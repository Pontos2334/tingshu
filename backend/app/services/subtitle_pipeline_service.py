import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy import delete as sql_delete, func, select

from app.config import settings as app_settings
from app.database import async_session
from app.db_models import Setting, SubtitleOutput, SubtitleProject, SubtitleSegment
from app.services.subtitle_asr_service import transcribe_whisper, transcribe_whisper_api, transcribe_xunfei
from app.services.subtitle_audio_extractor import extract_audio, probe_media
from app.services.subtitle_llm_service import SubtitleLLMError
from app.services.subtitle_polish_service import polish_segments
from app.services.subtitle_storage import build_relative_subtitle_path, delete_file, get_subtitle_full_path
from app.services.subtitle_translator_service import translate_segments

logger = logging.getLogger("tingshu.subtitle.pipeline")

_running_tasks: dict[int, asyncio.Task] = {}
_cancel_flags: dict[int, bool] = {}
_task_events: dict[int, list[asyncio.Queue]] = {}
_db_lock = asyncio.Lock()

TARGET_ALIASES = {
    "polish": "translate_polish",
    "polish_no_translate": "polish_source",
}
VALID_TARGETS = {"extract", "transcribe", "translate", "polish_source", "translate_polish", *TARGET_ALIASES.keys()}


@dataclass(frozen=True)
class SegmentCounts:
    total: int = 0
    translated: int = 0
    polished: int = 0


def normalize_target_step(target_step: str) -> str:
    return TARGET_ALIASES.get(target_step, target_step)


def plan_pipeline_steps(project: SubtitleProject, counts: SegmentCounts, target_step: str, force: bool = False) -> list[str]:
    target = normalize_target_step(target_step)
    if target not in {"extract", "transcribe", "translate", "polish_source", "translate_polish"}:
        raise ValueError("无效的目标步骤")

    steps: list[str] = []
    needs_segments = target in {"transcribe", "translate", "polish_source", "translate_polish"}
    needs_transcribe = target == "transcribe" or (needs_segments and counts.total == 0)

    if target == "extract":
        if not project.video_path:
            raise ValueError("没有可提取音频的视频文件")
        return ["extract"]

    if needs_transcribe:
        if not project.audio_path:
            if project.video_path:
                steps.append("extract")
            else:
                raise ValueError("请先上传视频、音频或导入 SRT")
        steps.append("transcribe")

    if target == "translate":
        steps.append("translate")
    elif target == "polish_source":
        steps.append("polish")
    elif target == "translate_polish":
        steps.extend(["polish", "translate"])

    return steps


def subscribe(project_id: int) -> asyncio.Queue:
    q = asyncio.Queue()
    _task_events.setdefault(project_id, []).append(q)
    return q


def unsubscribe(project_id: int, q: asyncio.Queue):
    if project_id in _task_events:
        try:
            _task_events[project_id].remove(q)
        except ValueError:
            pass
        if not _task_events[project_id]:
            del _task_events[project_id]


async def emit(project_id: int, event: dict):
    for q in _task_events.get(project_id, []):
        try:
            await q.put(event)
        except Exception:
            pass


def is_running(project_id: int) -> bool:
    return project_id in _running_tasks


def cancel_task(project_id: int):
    _cancel_flags[project_id] = True
    task = _running_tasks.get(project_id)
    if task and not task.done():
        task.cancel()


def is_cancel_requested(project_id: int) -> bool:
    return _cancel_flags.get(project_id, False)


def _cleanup_task(project_id: int):
    _running_tasks.pop(project_id, None)
    _cancel_flags.pop(project_id, None)


def start_pipeline(project_id: int, target_step: str, force: bool = False):
    if project_id in _running_tasks:
        return
    _cancel_flags[project_id] = False
    task = asyncio.create_task(_process_pipeline(project_id, target_step, force))
    _running_tasks[project_id] = task
    task.add_done_callback(lambda t: _cleanup_task(project_id))


async def _get_setting(key: str, default: str = "") -> str:
    async with async_session() as db:
        result = await db.execute(select(Setting).where(Setting.key == key))
        row = result.scalar_one_or_none()
        return row.value if row else default


async def get_segment_counts(db, project_id: int) -> SegmentCounts:
    total = (await db.execute(select(func.count(SubtitleSegment.id)).where(SubtitleSegment.project_id == project_id))).scalar() or 0
    translated = (
        await db.execute(
            select(func.count(SubtitleSegment.id)).where(
                SubtitleSegment.project_id == project_id,
                SubtitleSegment.translated_text.isnot(None),
                SubtitleSegment.translated_text != "",
            )
        )
    ).scalar() or 0
    polished = (
        await db.execute(
            select(func.count(SubtitleSegment.id)).where(
                SubtitleSegment.project_id == project_id,
                SubtitleSegment.polished_text.isnot(None),
                SubtitleSegment.polished_text != "",
            )
        )
    ).scalar() or 0
    return SegmentCounts(total=total, translated=translated, polished=polished)


def _resolve_asr_language(source_language: str, asr_engine: str) -> str | None:
    if not source_language or source_language == "auto":
        return "auto" if asr_engine == "xunfei" else None

    lang_map = {
        "zh": "zh", "en": "en", "ja": "ja", "ko": "ko",
        "fr": "fr", "de": "de", "es": "es",
    }
    xunfei_map = {"zh": "zh_cn", "en": "en_us"}

    if asr_engine == "xunfei":
        if source_language in xunfei_map:
            return xunfei_map[source_language]
        raise ValueError(f"讯飞语音仅支持中文和英文识别，不支持: {source_language}")

    return lang_map.get(source_language, source_language)


async def _load_segments(db, project_id: int) -> list[SubtitleSegment]:
    result = await db.execute(
        select(SubtitleSegment)
        .where(SubtitleSegment.project_id == project_id)
        .order_by(SubtitleSegment.segment_index)
    )
    return list(result.scalars().all())


async def _delete_outputs(db, project_id: int):
    result = await db.execute(select(SubtitleOutput).where(SubtitleOutput.project_id == project_id))
    for output in result.scalars().all():
        delete_file(output.file_path, "subtitle")
        await db.delete(output)


async def _commit(db):
    async with _db_lock:
        await db.commit()


async def _start_step(project_id: int, db, project: SubtitleProject, step: str, message: str):
    project.current_step = step
    project.error_message = None
    project.error_step = None
    project.error_code = None
    project.error_detail = None
    await _commit(db)
    await emit(project_id, {"type": "step_started", "step": step, "message": message})


async def _check_cancel(project_id: int, db, project: SubtitleProject) -> bool:
    if not is_cancel_requested(project_id):
        return False
    project.status = "canceled"
    project.current_step = None
    await _commit(db)
    await emit(project_id, {"type": "pipeline_canceled"})
    return True


async def _extract(project_id: int, db, project: SubtitleProject):
    await _start_step(project_id, db, project, "extract", "开始提取音频")
    if await _check_cancel(project_id, db, project):
        return

    audio_rel_path = build_relative_subtitle_path("wav")
    audio_full = get_subtitle_full_path(audio_rel_path)
    await extract_audio(project.video_path, audio_full, lambda e: emit(project_id, e))

    if project.audio_path:
        delete_file(project.audio_path, "subtitle")
    project.audio_path = audio_rel_path

    info = await probe_media(project.video_path)
    project.video_duration = info["duration"]
    project.video_size = info["size"]
    project.status = "audio_extracted"
    await _commit(db)
    await emit(project_id, {"type": "step_done", "step": "extract"})


async def _transcribe(project_id: int, db, project: SubtitleProject):
    await _start_step(project_id, db, project, "transcribe", "开始语音识别")
    if await _check_cancel(project_id, db, project):
        return

    if not project.audio_path:
        raise ValueError("没有可识别的音频文件")

    audio_full = get_subtitle_full_path(project.audio_path)
    asr_lang = _resolve_asr_language(project.source_language, project.asr_engine)

    if project.asr_engine == "whisper":
        from app.services.subtitle_runtime_check import check_local_whisper_gpu_runtime

        gpu_status = check_local_whisper_gpu_runtime()
        if not gpu_status["ok"]:
            raise RuntimeError(gpu_status["message"])
        result = await transcribe_whisper(audio_full, project.faster_whisper_model, asr_lang, lambda e: emit(project_id, e))
    elif project.asr_engine == "whisper_api":
        api_key = await _get_setting("whisper_api_key", app_settings.whisper_api_key)
        base_url = await _get_setting("whisper_api_base_url", app_settings.whisper_api_base_url)
        result = await transcribe_whisper_api(audio_full, api_key, base_url, asr_lang, lambda e: emit(project_id, e), model=project.whisper_api_model or "whisper-1")
    elif project.asr_engine == "xunfei":
        appid = await _get_setting("xunfei_appid", app_settings.xunfei_appid)
        api_key = await _get_setting("xunfei_api_key", app_settings.xunfei_api_key)
        api_secret = await _get_setting("xunfei_api_secret", app_settings.xunfei_api_secret)
        result = await transcribe_xunfei(audio_full, appid, api_key, api_secret, asr_lang or "zh_cn", lambda e: emit(project_id, e))
    else:
        raise ValueError(f"未知 ASR 引擎: {project.asr_engine}")

    await _delete_outputs(db, project_id)
    await db.execute(sql_delete(SubtitleSegment).where(SubtitleSegment.project_id == project_id))

    for i, seg in enumerate(result["segments"]):
        db.add(SubtitleSegment(
            project_id=project_id,
            segment_index=i,
            start_time=seg["start"],
            end_time=seg["end"],
            original_text=seg["text"],
        ))

    project.detected_language = result.get("language")
    project.status = "transcribed"
    await _commit(db)
    await emit(project_id, {"type": "step_done", "step": "transcribe", "segment_count": len(result["segments"])})


async def _polish(project_id: int, db, project: SubtitleProject, force: bool):
    await _start_step(project_id, db, project, "polish", "开始润色原文")
    if await _check_cancel(project_id, db, project):
        return

    segments = await _load_segments(db, project_id)
    if not segments:
        raise ValueError("没有可润色的字幕片段")

    await _delete_outputs(db, project_id)
    seg_dicts = [{"start": s.start_time, "end": s.end_time, "text": s.original_text} for s in segments]
    api_key = await _get_setting("deepseek_api_key", app_settings.deepseek_api_key)
    base_url = await _get_setting("deepseek_base_url", app_settings.deepseek_base_url)

    polished = await polish_segments(
        seg_dicts,
        api_key,
        base_url,
        project.translator_model,
        project.source_language,
        project.context_hint,
        lambda e: emit(project_id, e),
        project_id=project_id,
    )

    for seg_obj, pol in zip(segments, polished):
        if force or not seg_obj.polished_edited:
            seg_obj.polished_text = pol["text"]

    project.status = "polished"
    await _commit(db)
    await emit(project_id, {"type": "step_done", "step": "polish"})


async def _translate(project_id: int, db, project: SubtitleProject, force: bool):
    await _start_step(project_id, db, project, "translate", "开始翻译")
    if await _check_cancel(project_id, db, project):
        return

    segments = await _load_segments(db, project_id)
    if not segments:
        raise ValueError("没有可翻译的字幕片段")

    await _delete_outputs(db, project_id)
    seg_dicts = [
        {"start": s.start_time, "end": s.end_time, "text": s.polished_text or s.original_text}
        for s in segments
    ]
    api_key = await _get_setting("deepseek_api_key", app_settings.deepseek_api_key)
    base_url = await _get_setting("deepseek_base_url", app_settings.deepseek_base_url)

    translated = await translate_segments(
        seg_dicts,
        api_key,
        base_url,
        project.translator_model,
        project.target_language,
        project.context_hint,
        lambda e: emit(project_id, e),
        project_id=project_id,
    )

    for seg_obj, trans in zip(segments, translated):
        if force or not seg_obj.translated_edited:
            seg_obj.translated_text = trans["text"]

    project.status = "translated"
    await _commit(db)
    await emit(project_id, {"type": "step_done", "step": "translate"})


async def _process_pipeline(project_id: int, target_step: str, force: bool):
    canonical_target = normalize_target_step(target_step)
    logger.info("字幕管线启动: project_id=%s target=%s canonical=%s force=%s", project_id, target_step, canonical_target, force)

    async with async_session() as db:
        result = await db.execute(select(SubtitleProject).where(SubtitleProject.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            logger.error("字幕管线启动失败，项目不存在: project_id=%s", project_id)
            return

        current_step: str | None = None
        try:
            counts = await get_segment_counts(db, project_id)
            steps = plan_pipeline_steps(project, counts, canonical_target, force)
            await emit(project_id, {
                "type": "snapshot",
                "project_id": project_id,
                "status": project.status,
                "current_step": project.current_step,
                "target_step": canonical_target,
                "planned_steps": steps,
                "error_message": project.error_message,
                "error_step": project.error_step,
                "error_code": project.error_code,
                "error_detail": project.error_detail,
            })

            for step in steps:
                current_step = step
                if step == "extract":
                    await _extract(project_id, db, project)
                elif step == "transcribe":
                    await _transcribe(project_id, db, project)
                elif step == "polish":
                    await _polish(project_id, db, project, force)
                elif step == "translate":
                    await _translate(project_id, db, project, force)
                if project.status == "canceled":
                    return

            project.current_step = None
            project.error_message = None
            project.error_step = None
            project.error_code = None
            project.error_detail = None
            await _commit(db)

            counts = await get_segment_counts(db, project_id)
            await emit(project_id, {
                "type": "pipeline_done",
                "project_id": project_id,
                "status": project.status,
                "target_step": canonical_target,
                "segment_count": counts.total,
                "translated_count": counts.translated,
                "polished_count": counts.polished,
            })
            logger.info("字幕管线完成: project_id=%s target=%s status=%s", project_id, canonical_target, project.status)

        except asyncio.CancelledError:
            project.status = "canceled"
            project.current_step = None
            await _commit(db)
            await emit(project_id, {"type": "pipeline_canceled", "project_id": project_id})
            logger.info("字幕管线已取消: project_id=%s step=%s", project_id, current_step)

        except Exception as exc:
            code = getattr(exc, "code", exc.__class__.__name__)
            detail = getattr(exc, "detail", str(exc) or repr(exc))
            message = str(exc) or repr(exc)
            project.status = "failed"
            project.error_message = message[:500]
            project.error_step = current_step
            project.error_code = code
            project.error_detail = str(detail)[:4000]
            project.current_step = None
            await _commit(db)
            await emit(project_id, {
                "type": "pipeline_error",
                "project_id": project_id,
                "step": current_step,
                "code": code,
                "message": message,
                "detail": str(detail),
                "error": message,
            })
            if isinstance(exc, SubtitleLLMError):
                logger.exception(
                    "字幕管线失败: project_id=%s target=%s step=%s code=%s message=%s detail=%s",
                    project_id,
                    canonical_target,
                    current_step,
                    code,
                    message,
                    detail,
                )
            else:
                logger.exception("字幕管线失败: project_id=%s target=%s step=%s", project_id, canonical_target, current_step)
