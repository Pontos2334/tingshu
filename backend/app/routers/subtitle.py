import os
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.db_models import SubtitleProject, SubtitleSegment, SubtitleOutput
from app.models import (
    SubtitleProjectCreate, SubtitleProjectUpdate, SubtitleProjectOut, SubtitleProjectDetail,
    SubtitleSegmentOut, SubtitleSegmentUpdate,
    SubtitleProcessRequest, SubtitleExportRequest, SubtitleOutputOut,
)
from app.services.subtitle_audio_extractor import ALLOWED_VIDEO_EXTENSIONS, ALLOWED_AUDIO_EXTENSIONS
from app.services.subtitle_runtime_check import check_local_whisper_gpu_runtime
from app.services.subtitle_storage import (
    write_video_stream, write_audio_stream, write_subtitle_file,
    get_subtitle_full_path, delete_file,
)
from app.services.subtitle_export_service import generate_content, parse_srt
from app.services.subtitle_pipeline_service import (
    SegmentCounts, get_segment_counts, normalize_target_step, plan_pipeline_steps,
    start_pipeline, is_running, cancel_task, subscribe, unsubscribe,
)
from app.config import settings as app_settings

logger = logging.getLogger("tingshu.subtitle.router")

router = APIRouter()


def _check_video_ext(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_VIDEO_EXTENSIONS


def _check_audio_ext(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_AUDIO_EXTENSIONS


async def _delete_project_outputs(db: AsyncSession, project_id: int):
    out_result = await db.execute(select(SubtitleOutput).where(SubtitleOutput.project_id == project_id))
    for out in out_result.scalars().all():
        delete_file(out.file_path, "subtitle")
        await db.delete(out)


async def _clear_subtitle_data(db: AsyncSession, project_id: int, clear_segments: bool = True):
    await _delete_project_outputs(db, project_id)
    if clear_segments:
        from sqlalchemy import delete as sql_delete
        await db.execute(sql_delete(SubtitleSegment).where(SubtitleSegment.project_id == project_id))


def _clear_project_error(project: SubtitleProject):
    project.current_step = None
    project.error_message = None
    project.error_step = None
    project.error_code = None
    project.error_detail = None


# ── 项目 CRUD ──────────────────────────────────────────

@router.post("/projects", response_model=SubtitleProjectOut)
async def create_project(data: SubtitleProjectCreate, db: AsyncSession = Depends(get_db)):
    project = SubtitleProject(
        name=data.name,
        asr_engine=data.asr_engine,
        faster_whisper_model=data.faster_whisper_model,
        whisper_api_model=data.whisper_api_model,
        source_language=data.source_language,
        target_language=data.target_language,
        translator_model=data.translator_model,
        context_hint=data.context_hint,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return _project_to_out(project, SegmentCounts())


@router.get("/projects")
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(SubtitleProject)
    count_query = select(func.count(SubtitleProject.id))

    if search:
        like = f"%{search}%"
        query = query.where(SubtitleProject.name.ilike(like) | SubtitleProject.video_filename.ilike(like))
        count_query = count_query.where(SubtitleProject.name.ilike(like) | SubtitleProject.video_filename.ilike(like))

    total = (await db.execute(count_query)).scalar() or 0
    offset = (page - 1) * page_size
    result = await db.execute(query.order_by(SubtitleProject.created_at.desc()).offset(offset).limit(page_size))
    projects = result.scalars().all()

    items = []
    for p in projects:
        counts = await get_segment_counts(db, p.id)
        items.append(_project_to_out(p, counts))

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/projects/{project_id}", response_model=SubtitleProjectDetail)
async def get_project(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SubtitleProject).where(SubtitleProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "项目不存在")

    seg_result = await db.execute(
        select(SubtitleSegment).where(SubtitleSegment.project_id == project_id).order_by(SubtitleSegment.segment_index)
    )
    segments = seg_result.scalars().all()

    out_result = await db.execute(
        select(SubtitleOutput).where(SubtitleOutput.project_id == project_id).order_by(SubtitleOutput.created_at.desc())
    )
    outputs = out_result.scalars().all()
    counts = SegmentCounts(
        total=len(segments),
        translated=sum(1 for s in segments if s.translated_text),
        polished=sum(1 for s in segments if s.polished_text),
    )

    return SubtitleProjectDetail(
        id=project.id,
        name=project.name,
        video_path=project.video_path,
        audio_path=project.audio_path,
        video_filename=project.video_filename,
        video_duration=project.video_duration,
        video_size=project.video_size,
        status=project.status,
        current_step=project.current_step,
        error_message=project.error_message,
        error_step=project.error_step,
        error_code=project.error_code,
        error_detail=project.error_detail,
        asr_engine=project.asr_engine,
        faster_whisper_model=project.faster_whisper_model,
        whisper_api_model=project.whisper_api_model,
        source_language=project.source_language,
        detected_language=project.detected_language,
        target_language=project.target_language,
        translator_model=project.translator_model,
        context_hint=project.context_hint,
        segment_count=counts.total,
        translated_count=counts.translated,
        polished_count=counts.polished,
        created_at=project.created_at,
        updated_at=project.updated_at,
        segments=[SubtitleSegmentOut.model_validate(s) for s in segments],
        outputs=[SubtitleOutputOut.model_validate(o) for o in outputs],
    )


@router.put("/projects/{project_id}", response_model=SubtitleProjectOut)
async def update_project(project_id: int, data: SubtitleProjectUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SubtitleProject).where(SubtitleProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "项目不存在")

    update_data = data.model_dump(exclude_none=True)
    for key, value in update_data.items():
        setattr(project, key, value)
    await db.commit()
    await db.refresh(project)

    counts = await get_segment_counts(db, project_id)
    return _project_to_out(project, counts)


@router.delete("/projects/{project_id}")
async def delete_project(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SubtitleProject).where(SubtitleProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "项目不存在")

    if is_running(project_id):
        raise HTTPException(409, "项目正在处理中，请先取消")

    # Delete files
    if project.video_path:
        delete_file(project.video_path, "video")
    if project.audio_path:
        delete_file(project.audio_path, "subtitle")

    # Delete output files
    out_result = await db.execute(select(SubtitleOutput).where(SubtitleOutput.project_id == project_id))
    for out in out_result.scalars().all():
        delete_file(out.file_path, "subtitle")

    await db.delete(project)
    await db.commit()
    return {"message": "项目已删除"}


# ── 视频上传 ──────────────────────────────────────────

@router.post("/projects/{project_id}/video")
async def upload_video(project_id: int, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SubtitleProject).where(SubtitleProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "项目不存在")

    if not _check_video_ext(file.filename):
        raise HTTPException(400, f"不支持的视频格式，支持: {', '.join(ALLOWED_VIDEO_EXTENSIONS)}")

    # Delete old video if exists
    if project.video_path:
        delete_file(project.video_path, "video")
    if project.audio_path:
        delete_file(project.audio_path, "subtitle")

    max_bytes = app_settings.max_video_size_mb * 1024 * 1024
    try:
        rel_path, total_size = await write_video_stream(file.filename, file, max_bytes)
    except ValueError as e:
        raise HTTPException(400, str(e))

    project.video_path = rel_path
    project.audio_path = None
    project.video_filename = file.filename
    project.video_duration = None
    project.video_size = total_size
    project.status = "uploaded"
    _clear_project_error(project)
    await _clear_subtitle_data(db, project_id, clear_segments=True)
    await db.commit()

    return {"message": "视频上传成功", "video_path": rel_path, "size": total_size}


# ── 音频上传 ──────────────────────────────────────────

@router.post("/projects/{project_id}/audio")
async def upload_audio(project_id: int, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SubtitleProject).where(SubtitleProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "项目不存在")

    if not _check_audio_ext(file.filename):
        raise HTTPException(400, f"不支持的音频格式，支持: {', '.join(sorted(ALLOWED_AUDIO_EXTENSIONS))}")

    # Delete old audio if exists
    if project.video_path:
        delete_file(project.video_path, "video")
    if project.audio_path:
        delete_file(project.audio_path, "subtitle")

    max_bytes = app_settings.max_video_size_mb * 1024 * 1024
    try:
        rel_path, total_size = await write_audio_stream(file.filename, file, max_bytes)
    except ValueError as e:
        raise HTTPException(400, str(e))

    project.video_path = None
    project.audio_path = rel_path
    project.video_filename = file.filename
    project.video_duration = None
    project.video_size = total_size
    project.status = "audio_extracted"
    _clear_project_error(project)
    await _clear_subtitle_data(db, project_id, clear_segments=True)
    await db.commit()

    return {"message": "音频上传成功", "audio_path": rel_path, "size": total_size}


# ── SRT 导入 ──────────────────────────────────────────

@router.post("/projects/{project_id}/import-srt")
async def import_srt(project_id: int, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SubtitleProject).where(SubtitleProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "项目不存在")

    content = (await file.read()).decode("utf-8-sig")
    segments = parse_srt(content)
    if not segments:
        raise HTTPException(400, "无法解析 SRT 文件或文件为空")

    await _clear_subtitle_data(db, project_id, clear_segments=True)

    for i, seg in enumerate(segments):
        db.add(SubtitleSegment(
            project_id=project_id,
            segment_index=i,
            start_time=seg["start"],
            end_time=seg["end"],
            original_text=seg["text"],
        ))

    project.status = "transcribed"
    _clear_project_error(project)
    await db.commit()

    return {"message": "SRT 导入成功", "segment_count": len(segments)}


# ── 本地 Whisper GPU 诊断 ──────────────────────────────

@router.get("/runtime/local-whisper")
async def local_whisper_runtime():
    """Return local Whisper GPU runtime diagnostics."""
    return check_local_whisper_gpu_runtime()


# ── 管线处理 ──────────────────────────────────────────

@router.post("/projects/{project_id}/process")
async def process_project(project_id: int, data: SubtitleProcessRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SubtitleProject).where(SubtitleProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "项目不存在")

    if is_running(project_id):
        raise HTTPException(409, "项目正在处理中")

    if data.target_step not in {"extract", "transcribe", "translate", "polish_source", "translate_polish", "polish", "polish_no_translate"}:
        raise HTTPException(400, "无效的目标步骤")

    target_step = normalize_target_step(data.target_step)
    counts = await get_segment_counts(db, project_id)
    try:
        planned_steps = plan_pipeline_steps(project, counts, target_step, data.force)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    if project.asr_engine == "whisper" and "transcribe" in planned_steps:
        gpu_status = check_local_whisper_gpu_runtime()
        if not gpu_status["ok"]:
            raise HTTPException(400, gpu_status["message"])

    start_pipeline(project_id, target_step, data.force)
    return {"message": "管线已启动", "target_step": target_step, "planned_steps": planned_steps}


@router.post("/projects/{project_id}/cancel")
async def cancel_project(project_id: int, db: AsyncSession = Depends(get_db)):
    if not is_running(project_id):
        raise HTTPException(409, "项目未在处理中")
    cancel_task(project_id)
    return {"message": "取消请求已发送"}


@router.get("/projects/{project_id}/events")
async def project_events(project_id: int, db: AsyncSession = Depends(get_db)):
    async def event_generator():
        import json as _json
        # Send initial snapshot so client always gets current state
        proj_result = await db.execute(select(SubtitleProject).where(SubtitleProject.id == project_id))
        proj = proj_result.scalar_one_or_none()
        if proj:
            counts = await get_segment_counts(db, project_id)
            yield f"data: {_json.dumps({'type': 'snapshot', 'project_id': project_id, 'status': proj.status, 'current_step': proj.current_step, 'error_message': proj.error_message, 'error_step': proj.error_step, 'error_code': proj.error_code, 'error_detail': proj.error_detail, 'segment_count': counts.total, 'translated_count': counts.translated, 'polished_count': counts.polished}, ensure_ascii=False)}\n\n"

        queue = subscribe(project_id)
        try:
            while True:
                event = await queue.get()
                yield f"data: {_json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") in ("pipeline_done", "pipeline_error", "pipeline_canceled"):
                    break
        finally:
            unsubscribe(project_id, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── 字幕片段 ──────────────────────────────────────────

@router.get("/projects/{project_id}/segments", response_model=list[SubtitleSegmentOut])
async def get_segments(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SubtitleSegment).where(SubtitleSegment.project_id == project_id).order_by(SubtitleSegment.segment_index)
    )
    return [SubtitleSegmentOut.model_validate(s) for s in result.scalars().all()]


@router.put("/projects/{project_id}/segments/{segment_id}", response_model=SubtitleSegmentOut)
async def update_segment(project_id: int, segment_id: int, data: SubtitleSegmentUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SubtitleSegment).where(SubtitleSegment.id == segment_id, SubtitleSegment.project_id == project_id)
    )
    segment = result.scalar_one_or_none()
    if not segment:
        raise HTTPException(404, "片段不存在")

    update_data = data.model_dump(exclude_none=True)
    for key, value in update_data.items():
        setattr(segment, key, value)
        if key == "original_text":
            segment.original_edited = True
        elif key == "polished_text":
            segment.polished_edited = True
        elif key == "translated_text":
            segment.translated_edited = True
    segment.is_edited = True
    await _delete_project_outputs(db, project_id)
    await db.commit()
    await db.refresh(segment)
    return SubtitleSegmentOut.model_validate(segment)


# ── 导出 ──────────────────────────────────────────

@router.post("/projects/{project_id}/export")
async def export_subtitles(project_id: int, data: SubtitleExportRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SubtitleProject).where(SubtitleProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "项目不存在")

    seg_result = await db.execute(
        select(SubtitleSegment).where(SubtitleSegment.project_id == project_id).order_by(SubtitleSegment.segment_index)
    )
    segments = seg_result.scalars().all()
    if not segments:
        raise HTTPException(400, "没有可导出的字幕片段")

    seg_dicts = [
        {
            "start_time": s.start_time,
            "end_time": s.end_time,
            "text": s.original_text,
            "original_text": s.original_text,
            "translated_text": s.translated_text,
            "polished_text": s.polished_text,
        }
        for s in segments
    ]

    content = generate_content(seg_dicts, data.format, data.variant)
    rel_path, _ = await write_subtitle_file(content, data.format)

    output = SubtitleOutput(
        project_id=project_id,
        format=data.format,
        variant=data.variant,
        file_path=rel_path,
        file_size=len(content.encode("utf-8")),
    )
    db.add(output)
    await db.commit()
    await db.refresh(output)

    return {"message": "导出成功", "output_id": output.id, "file_size": output.file_size}


@router.get("/projects/{project_id}/outputs", response_model=list[SubtitleOutputOut])
async def list_outputs(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SubtitleOutput).where(SubtitleOutput.project_id == project_id).order_by(SubtitleOutput.created_at.desc())
    )
    return [SubtitleOutputOut.model_validate(o) for o in result.scalars().all()]


@router.get("/projects/{project_id}/outputs/{output_id}/download")
async def download_output(project_id: int, output_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SubtitleOutput).where(SubtitleOutput.id == output_id, SubtitleOutput.project_id == project_id)
    )
    output = result.scalar_one_or_none()
    if not output:
        raise HTTPException(404, "输出文件不存在")

    full_path = get_subtitle_full_path(output.file_path)
    if not os.path.exists(full_path):
        raise HTTPException(404, "文件已丢失")

    ext_map = {"srt": ".srt", "vtt": ".vtt", "txt": ".txt"}
    ext = ext_map.get(output.format, ".txt")
    variant_map = {"original": "原文", "translated": "译文", "bilingual": "双语", "polished": "润色"}
    variant_name = variant_map.get(output.variant, output.variant)

    # Get project name for filename
    proj_result = await db.execute(select(SubtitleProject).where(SubtitleProject.id == project_id))
    proj = proj_result.scalar_one_or_none()
    proj_name = proj.name if proj else "subtitle"

    filename = f"{proj_name}_{variant_name}{ext}"
    return FileResponse(full_path, filename=filename, media_type="application/octet-stream")


# ── Helper ──────────────────────────────────────────

def _project_to_out(project: SubtitleProject, counts: SegmentCounts | int) -> SubtitleProjectOut:
    if isinstance(counts, int):
        counts = SegmentCounts(total=counts)
    return SubtitleProjectOut(
        id=project.id,
        name=project.name,
        video_filename=project.video_filename,
        video_duration=project.video_duration,
        video_size=project.video_size,
        status=project.status,
        current_step=project.current_step,
        asr_engine=project.asr_engine,
        source_language=project.source_language,
        target_language=project.target_language,
        segment_count=counts.total,
        translated_count=counts.translated,
        polished_count=counts.polished,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )
