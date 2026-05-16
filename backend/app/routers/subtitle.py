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
from app.services.subtitle_audio_extractor import ALLOWED_VIDEO_EXTENSIONS
from app.services.subtitle_storage import (
    write_video_file, write_video_stream, write_subtitle_file,
    get_video_full_path, get_subtitle_full_path, delete_file,
)
from app.services.subtitle_export_service import generate_content, parse_srt
from app.services.subtitle_pipeline_service import (
    start_pipeline, is_running, cancel_task, subscribe, unsubscribe, emit,
)
from app.config import settings as app_settings

logger = logging.getLogger("tingshu.subtitle.router")

router = APIRouter()


def _check_video_ext(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_VIDEO_EXTENSIONS


# ── 项目 CRUD ──────────────────────────────────────────

@router.post("/projects", response_model=SubtitleProjectOut)
async def create_project(data: SubtitleProjectCreate, db: AsyncSession = Depends(get_db)):
    project = SubtitleProject(
        name=data.name,
        asr_engine=data.asr_engine,
        faster_whisper_model=data.faster_whisper_model,
        whisper_api_model=data.whisper_api_model,
        target_language=data.target_language,
        translator_model=data.translator_model,
        context_hint=data.context_hint,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return _project_to_out(project, 0)


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

    # Get segment counts
    items = []
    for p in projects:
        cnt_result = await db.execute(
            select(func.count(SubtitleSegment.id)).where(SubtitleSegment.project_id == p.id)
        )
        seg_count = cnt_result.scalar() or 0
        items.append(_project_to_out(p, seg_count))

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
        asr_engine=project.asr_engine,
        faster_whisper_model=project.faster_whisper_model,
        whisper_api_model=project.whisper_api_model,
        detected_language=project.detected_language,
        target_language=project.target_language,
        translator_model=project.translator_model,
        context_hint=project.context_hint,
        segment_count=len(segments),
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

    cnt_result = await db.execute(select(func.count(SubtitleSegment.id)).where(SubtitleSegment.project_id == project_id))
    seg_count = cnt_result.scalar() or 0
    return _project_to_out(project, seg_count)


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

    max_bytes = app_settings.max_video_size_mb * 1024 * 1024
    try:
        rel_path, total_size = await write_video_stream(file.filename, file, max_bytes)
    except ValueError as e:
        raise HTTPException(400, str(e))

    project.video_path = rel_path
    project.video_filename = file.filename
    project.video_size = total_size
    project.status = "uploaded"
    await db.commit()

    return {"message": "视频上传成功", "video_path": rel_path, "size": total_size}


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

    # Clear old segments
    from sqlalchemy import delete as sql_delete
    await db.execute(sql_delete(SubtitleSegment).where(SubtitleSegment.project_id == project_id))

    for i, seg in enumerate(segments):
        db.add(SubtitleSegment(
            project_id=project_id,
            segment_index=i,
            start_time=seg["start"],
            end_time=seg["end"],
            original_text=seg["text"],
        ))

    project.status = "transcribed"
    await db.commit()

    return {"message": "SRT 导入成功", "segment_count": len(segments)}


# ── 管线处理 ──────────────────────────────────────────

@router.post("/projects/{project_id}/process")
async def process_project(project_id: int, data: SubtitleProcessRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SubtitleProject).where(SubtitleProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "项目不存在")

    if is_running(project_id):
        raise HTTPException(409, "项目正在处理中")

    if data.target_step not in ("extract", "transcribe", "translate"):
        raise HTTPException(400, "无效的目标步骤")

    # Validate prerequisites
    if data.target_step in ("transcribe", "translate") and not project.audio_path and not project.video_path:
        if not data.force:
            # Allow translate if segments already exist (e.g. from SRT import)
            if data.target_step == "translate":
                cnt_result = await db.execute(
                    select(func.count(SubtitleSegment.id)).where(SubtitleSegment.project_id == project_id)
                )
                if (cnt_result.scalar() or 0) > 0:
                    pass  # segments exist, allow translate
                else:
                    raise HTTPException(400, "请先上传视频或导入 SRT")
            else:
                raise HTTPException(400, "请先上传视频或导入 SRT")

    start_pipeline(project_id, data.target_step, data.force)
    return {"message": "管线已启动", "target_step": data.target_step}


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
            yield f"data: {_json.dumps({'type': 'snapshot', 'project_id': project_id, 'status': proj.status, 'current_step': proj.current_step}, ensure_ascii=False)}\n\n"

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
    segment.is_edited = True
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
    variant_map = {"original": "原文", "translated": "译文", "bilingual": "双语"}
    variant_name = variant_map.get(output.variant, output.variant)

    # Get project name for filename
    proj_result = await db.execute(select(SubtitleProject).where(SubtitleProject.id == project_id))
    proj = proj_result.scalar_one_or_none()
    proj_name = proj.name if proj else "subtitle"

    filename = f"{proj_name}_{variant_name}{ext}"
    return FileResponse(full_path, filename=filename, media_type="application/octet-stream")


# ── Helper ──────────────────────────────────────────

def _project_to_out(project: SubtitleProject, segment_count: int) -> SubtitleProjectOut:
    return SubtitleProjectOut(
        id=project.id,
        name=project.name,
        video_filename=project.video_filename,
        video_duration=project.video_duration,
        video_size=project.video_size,
        status=project.status,
        current_step=project.current_step,
        asr_engine=project.asr_engine,
        target_language=project.target_language,
        segment_count=segment_count,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )
