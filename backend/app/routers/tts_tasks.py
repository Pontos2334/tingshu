import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.db_models import SynthesisTask, SynthesisChunk, AudioRecord
from app.models import (
    SynthesizeLongRequest, SynthesisTaskOut, SynthesisChunkOut, SynthesisTaskDetail,
)
from app.services.audio_storage import delete_audio_file, get_audio_full_path
from app.services.text_service import split_text
from app.services import synthesis_service

router = APIRouter()
logger = logging.getLogger("tingshu.tts_tasks")


def _task_to_out(task: SynthesisTask) -> dict:
    return {
        "task_id": task.task_id,
        "title": task.title,
        "total_chunks": task.total_chunks,
        "completed_chunks": task.completed_chunks,
        "failed_chunks": task.failed_chunks,
        "status": task.status,
        "voice_name": task.voice_name,
        "voice_id": task.voice_id,
        "model": task.model,
        "styles": task.styles,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def _chunk_to_out(chunk: SynthesisChunk) -> dict:
    preview = chunk.text_content[:100] if chunk.text_content else ""
    return {
        "chunk_index": chunk.chunk_index,
        "text_preview": preview,
        "status": chunk.status,
        "retry_count": chunk.retry_count,
        "audio_record_id": chunk.audio_record_id,
        "error_message": chunk.error_message,
    }


@router.post("/create-task")
async def create_task(req: SynthesizeLongRequest, db: AsyncSession = Depends(get_db)):
    import uuid

    chunks = split_text(req.text, req.chunk_size)
    if not chunks:
        raise HTTPException(status_code=400, detail="文本为空")

    task_id = str(uuid.uuid4())
    title = req.text[:50].replace("\n", " ").strip()

    task = SynthesisTask(
        task_id=task_id,
        title=title,
        full_text=req.text,
        chunk_size=req.chunk_size,
        total_chunks=len(chunks),
        status="pending",
        voice_name=req.voice,
        voice_id=req.voice_id,
        model=req.model,
        styles=json.dumps(req.styles),
    )
    db.add(task)

    for i, chunk_text in enumerate(chunks):
        chunk = SynthesisChunk(
            task_id=task_id,
            chunk_index=i,
            text_content=chunk_text,
            status="pending",
        )
        db.add(chunk)

    await db.commit()

    # 启动后台处理
    synthesis_service.start_task(task_id)

    return {"task_id": task_id, "total_chunks": len(chunks)}


@router.get("/tasks")
async def list_tasks(page: int = 1, size: int = 20, db: AsyncSession = Depends(get_db)):
    offset = (page - 1) * size
    result = await db.execute(
        select(SynthesisTask)
        .order_by(SynthesisTask.created_at.desc())
        .offset(offset)
        .limit(size)
    )
    tasks = result.scalars().all()

    # 统计总数
    from sqlalchemy import func
    count_result = await db.execute(select(func.count(SynthesisTask.id)))
    total = count_result.scalar() or 0

    return {
        "items": [_task_to_out(t) for t in tasks],
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SynthesisTask).where(SynthesisTask.task_id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    result = await db.execute(
        select(SynthesisChunk)
        .where(SynthesisChunk.task_id == task_id)
        .order_by(SynthesisChunk.chunk_index)
    )
    chunks = result.scalars().all()

    data = _task_to_out(task)
    data["chunks"] = [_chunk_to_out(c) for c in chunks]
    data["is_running"] = synthesis_service.is_running(task_id)
    return data


@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SynthesisTask).where(SynthesisTask.task_id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    try:
        await synthesis_service.resume_task(task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"message": "任务已恢复", "task_id": task_id}


@router.post("/tasks/{task_id}/retry-failed")
async def retry_failed(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SynthesisTask).where(SynthesisTask.task_id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    try:
        await synthesis_service.retry_failed_chunks(task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"message": "失败段已重新排队", "task_id": task_id}


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SynthesisTask).where(SynthesisTask.task_id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status != "running":
        raise HTTPException(status_code=400, detail="任务未在运行中")

    synthesis_service.cancel_task(task_id)

    # 立即更新状态（后台协程会在 chunk 间隙确认取消）
    task.status = "canceled"
    await db.commit()

    return {"message": "任务已取消", "task_id": task_id}


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SynthesisTask).where(SynthesisTask.task_id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status == "running" or synthesis_service.is_running(task_id):
        raise HTTPException(status_code=409, detail="任务运行中，请先取消")

    result = await db.execute(
        select(AudioRecord).where(AudioRecord.task_id == task_id)
    )
    records = result.scalars().all()
    for record in records:
        if record.file_path and os.path.exists(get_audio_full_path(record.file_path)):
            try:
                delete_audio_file(record.file_path)
            except OSError as e:
                logger.warning(f"删除任务音频文件失败 {record.file_path}: {e}")
        await db.delete(record)

    chunk_result = await db.execute(
        select(SynthesisChunk).where(SynthesisChunk.task_id == task_id)
    )
    for chunk in chunk_result.scalars().all():
        await db.delete(chunk)

    await db.delete(task)
    await db.commit()

    return {"message": "任务已删除"}


@router.get("/tasks/{task_id}/events")
async def task_events(task_id: str, db: AsyncSession = Depends(get_db)):
    # 验证任务存在
    result = await db.execute(
        select(SynthesisTask).where(SynthesisTask.task_id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    async def event_generator():
        # 先推送当前快照
        result_chunks = await db.execute(
            select(SynthesisChunk)
            .where(SynthesisChunk.task_id == task_id)
            .order_by(SynthesisChunk.chunk_index)
        )
        chunks = result_chunks.scalars().all()

        snapshot = {
            "type": "snapshot",
            "task": _task_to_out(task),
            "chunks": [_chunk_to_out(c) for c in chunks],
            "is_running": synthesis_service.is_running(task_id),
        }
        yield f"data: {json.dumps(snapshot, default=str)}\n\n"

        # 订阅增量事件
        queue = synthesis_service.subscribe(task_id)
        try:
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event, default=str)}\n\n"
                # 如果任务结束，推送完毕后关闭
                if event.get("type") in ("task_done", "task_canceled", "task_error"):
                    break
        except asyncio.CancelledError:
            pass
        finally:
            synthesis_service.unsubscribe(task_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
