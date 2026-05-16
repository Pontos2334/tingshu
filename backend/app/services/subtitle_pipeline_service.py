import asyncio
import logging
import os

from app.database import async_session
from app.db_models import SubtitleProject, SubtitleSegment, Setting
from app.services.subtitle_audio_extractor import extract_audio, probe_media
from app.services.subtitle_asr_service import transcribe_whisper, transcribe_whisper_api, transcribe_xunfei
from app.services.subtitle_translator_service import translate_segments
from app.services.subtitle_export_service import generate_content
from app.services.subtitle_storage import (
    get_video_storage_root, build_relative_subtitle_path, get_subtitle_full_path,
)
from app.config import settings as app_settings

logger = logging.getLogger("tingshu.subtitle.pipeline")

_running_tasks: dict[int, asyncio.Task] = {}
_cancel_flags: dict[int, bool] = {}
_task_events: dict[int, list[asyncio.Queue]] = {}
_db_lock = asyncio.Lock()


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
        result = await db.execute(__import__("sqlalchemy").select(Setting).where(Setting.key == key))
        row = result.scalar_one_or_none()
        return row.value if row else default


STEP_ORDER = {"extract": 0, "transcribe": 1, "translate": 2}


async def _process_pipeline(project_id: int, target_step: str, force: bool):
    logger.info(f"字幕管线启动: project_id={project_id}, target={target_step}, force={force}")

    async with async_session() as db:
        from sqlalchemy import select
        result = await db.execute(select(SubtitleProject).where(SubtitleProject.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            logger.error(f"项目不存在: {project_id}")
            return

        target_idx = STEP_ORDER.get(target_step, 2)

        try:
            # Send snapshot
            await emit(project_id, {
                "type": "snapshot",
                "project_id": project_id,
                "status": project.status,
                "target_step": target_step,
            })

            # Step 1: Extract audio
            if target_idx >= 0 and project.video_path:
                need_extract = force or project.status in ("draft", "uploaded", "failed", "canceled")
                if need_extract:
                    project.current_step = "extracting"
                    project.status = "uploaded"
                    async with _db_lock:
                        await db.commit()

                    await emit(project_id, {"type": "step_started", "step": "extract"})

                    if is_cancel_requested(project_id):
                        project.status = "canceled"
                        async with _db_lock:
                            await db.commit()
                        await emit(project_id, {"type": "pipeline_canceled"})
                        return

                    audio_rel_path = build_relative_subtitle_path("wav")
                    audio_full = get_subtitle_full_path(audio_rel_path)

                    await extract_audio(project.video_path, audio_full, lambda e: emit(project_id, e))

                    project.audio_path = audio_rel_path
                    project.status = "audio_extracted"

                    # Probe for duration
                    info = await probe_media(project.video_path)
                    project.video_duration = info["duration"]
                    project.video_size = info["size"]

                    async with _db_lock:
                        await db.commit()

                    await emit(project_id, {"type": "step_done", "step": "extract"})

            # Step 2: Transcribe
            if target_idx >= 1:
                need_transcribe = force or project.status in ("draft", "uploaded", "audio_extracted", "failed", "canceled")
                if need_transcribe and project.audio_path:
                    project.current_step = "transcribing"
                    async with _db_lock:
                        await db.commit()

                    await emit(project_id, {"type": "step_started", "step": "transcribe"})

                    if is_cancel_requested(project_id):
                        project.status = "canceled"
                        async with _db_lock:
                            await db.commit()
                        await emit(project_id, {"type": "pipeline_canceled"})
                        return

                    audio_full = get_subtitle_full_path(project.audio_path)

                    if project.asr_engine == "whisper":
                        result = await transcribe_whisper(audio_full, project.faster_whisper_model, None, lambda e: emit(project_id, e))
                    elif project.asr_engine == "whisper_api":
                        api_key = await _get_setting("whisper_api_key", app_settings.whisper_api_key)
                        base_url = await _get_setting("whisper_api_base_url", app_settings.whisper_api_base_url)
                        result = await transcribe_whisper_api(audio_full, api_key, base_url, None, lambda e: emit(project_id, e), model=project.whisper_api_model or "whisper-1")
                    elif project.asr_engine == "xunfei":
                        appid = await _get_setting("xunfei_appid", app_settings.xunfei_appid)
                        api_key = await _get_setting("xunfei_api_key", app_settings.xunfei_api_key)
                        api_secret = await _get_setting("xunfei_api_secret", app_settings.xunfei_api_secret)
                        result = await transcribe_xunfei(audio_full, appid, api_key, api_secret, "zh_cn", lambda e: emit(project_id, e))
                    else:
                        raise ValueError(f"未知 ASR 引擎: {project.asr_engine}")

                    # Store segments
                    # Clear old segments if force
                    if force:
                        from sqlalchemy import delete as sql_delete
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
                    async with _db_lock:
                        await db.commit()

                    await emit(project_id, {"type": "step_done", "step": "transcribe", "segment_count": len(result["segments"])})

            # Step 3: Translate
            if target_idx >= 2:
                need_translate = force or project.status in ("transcribed", "audio_extracted", "translated", "completed", "failed", "canceled")
                if need_translate:
                    project.current_step = "translating"
                    async with _db_lock:
                        await db.commit()

                    await emit(project_id, {"type": "step_started", "step": "translate"})

                    if is_cancel_requested(project_id):
                        project.status = "canceled"
                        async with _db_lock:
                            await db.commit()
                        await emit(project_id, {"type": "pipeline_canceled"})
                        return

                    # Get segments
                    seg_result = await db.execute(
                        __import__("sqlalchemy").select(SubtitleSegment)
                        .where(SubtitleSegment.project_id == project_id)
                        .order_by(SubtitleSegment.segment_index)
                    )
                    segments = seg_result.scalars().all()

                    if not segments:
                        raise ValueError("没有可翻译的字幕片段")

                    seg_dicts = [
                        {"start": s.start_time, "end": s.end_time, "text": s.original_text}
                        for s in segments
                    ]

                    # Get translation config
                    api_key = await _get_setting("deepseek_api_key", app_settings.deepseek_api_key)
                    base_url = await _get_setting("deepseek_base_url", app_settings.deepseek_base_url)

                    translated = await translate_segments(
                        seg_dicts, api_key, base_url,
                        project.translator_model, project.target_language,
                        project.context_hint, lambda e: emit(project_id, e),
                    )

                    # Update segments with translations
                    for seg_obj, trans in zip(segments, translated):
                        if not seg_obj.is_edited or force:
                            seg_obj.translated_text = trans["text"]

                    project.status = "translated"
                    async with _db_lock:
                        await db.commit()

                    await emit(project_id, {"type": "step_done", "step": "translate"})

            # Final status
            project.current_step = None
            if project.status in ("translated",):
                project.status = "completed"
            async with _db_lock:
                await db.commit()

            await emit(project_id, {
                "type": "pipeline_done",
                "project_id": project_id,
                "status": project.status,
            })
            logger.info(f"字幕管线完成: project_id={project_id}, status={project.status}")

        except asyncio.CancelledError:
            project.status = "canceled"
            project.current_step = None
            async with _db_lock:
                await db.commit()
            await emit(project_id, {"type": "pipeline_canceled"})
            logger.info(f"字幕管线已取消: project_id={project_id}")

        except Exception as e:
            project.status = "failed"
            project.error_message = str(e)[:500]
            project.current_step = None
            async with _db_lock:
                await db.commit()
            await emit(project_id, {"type": "pipeline_error", "error": str(e)})
            logger.error(f"字幕管线失败: project_id={project_id}, error={e}")
