import asyncio
import json
import logging
import os

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.db_models import AudioRecord, PlaylistTrack, SynthesisChunk, SynthesisTask
from app.models import AudioGroupDetailOut, AudioGroupSummaryOut, AudioRecordOut
from app.services import merge_service, synthesis_service
from app.services.audio_storage import delete_audio_file, get_audio_full_path

logger = logging.getLogger("tingshu.audio")

router = APIRouter()


def _build_group_key(record: AudioRecord) -> str:
    if record.group_id:
        return record.group_id
    if record.task_id:
        return record.task_id
    return f"record-{record.id}"


def _sort_group_records(records: list[AudioRecord]) -> list[AudioRecord]:
    return sorted(
        records,
        key=lambda item: (
            item.chunk_index if item.chunk_index is not None else 10**9,
            item.created_at or "",
            item.id or 0,
        ),
    )


def _build_group_summary(group_key: str, records: list[AudioRecord]) -> dict:
    ordered = _sort_group_records(records)
    first = ordered[0]
    total_duration = sum(item.duration or 0 for item in ordered)
    return {
        "group_id": group_key,
        "title": first.title,
        "voice_name": first.voice_name,
        "clip_count": len(ordered),
        "total_duration": round(total_duration, 2),
        "created_at": first.created_at,
        "has_favorite": any(item.is_favorite for item in ordered),
        "source_type": "long_text" if len(ordered) > 1 or first.task_id or first.group_id else "single",
    }


def _match_group_query(records: list[AudioRecord], query: str) -> bool:
    if not query:
        return True

    query_lower = query.lower()
    for item in records:
        if any(
            value and query_lower in value.lower()
            for value in [item.title, item.voice_name, item.text_content]
        ):
            return True
    return False


async def _load_group_records(group_id: str, db: AsyncSession) -> list[AudioRecord]:
    if group_id.startswith("record-"):
        record_id = int(group_id.replace("record-", "", 1))
        result = await db.execute(select(AudioRecord).where(AudioRecord.id == record_id))
        record = result.scalar_one_or_none()
        return [record] if record else []

    result = await db.execute(
        select(AudioRecord)
        .where((AudioRecord.group_id == group_id) | (AudioRecord.task_id == group_id))
        .order_by(AudioRecord.chunk_index, AudioRecord.created_at, AudioRecord.id)
    )
    return result.scalars().all()


@router.get("/records", response_model=list[AudioRecordOut])
async def get_records(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * size
    result = await db.execute(
        select(AudioRecord)
        .order_by(AudioRecord.created_at.desc())
        .offset(offset)
        .limit(size)
    )
    return result.scalars().all()


@router.get("/records/{record_id}", response_model=AudioRecordOut)
async def get_record(record_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AudioRecord).where(AudioRecord.id == record_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    return record


@router.get("/file/{record_id}")
async def get_audio_file(record_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AudioRecord).where(AudioRecord.id == record_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    full_path = get_audio_full_path(record.file_path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="音频文件不存在")

    return FileResponse(full_path, media_type="audio/wav", filename=f"{record.title}.wav")


@router.delete("/records/{record_id}")
async def delete_record(record_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AudioRecord).where(AudioRecord.id == record_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    full_path = get_audio_full_path(record.file_path)
    if os.path.exists(full_path):
        try:
            delete_audio_file(record.file_path)
        except OSError as e:
            logger.warning(f"删除文件失败 {full_path}: {e}")

    await db.delete(record)
    await db.commit()
    return {"message": "已删除"}


@router.put("/records/{record_id}/favorite")
async def toggle_favorite(record_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AudioRecord).where(AudioRecord.id == record_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    record.is_favorite = not record.is_favorite
    await db.commit()
    await db.refresh(record)
    return {"is_favorite": record.is_favorite}


@router.get("/favorites", response_model=list[AudioRecordOut])
async def get_favorites(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * size
    result = await db.execute(
        select(AudioRecord)
        .where(AudioRecord.is_favorite == True)
        .order_by(AudioRecord.created_at.desc())
        .offset(offset)
        .limit(size)
    )
    return result.scalars().all()


@router.get("/groups", response_model=dict)
async def get_audio_groups(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None),
    favorite: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AudioRecord).order_by(AudioRecord.created_at.desc(), AudioRecord.id.desc())
    )
    records = result.scalars().all()

    grouped: dict[str, list[AudioRecord]] = {}
    for record in records:
        grouped.setdefault(_build_group_key(record), []).append(record)

    summaries = []
    for group_key, group_records in grouped.items():
        if favorite is True and not any(item.is_favorite for item in group_records):
            continue
        if favorite is False and any(item.is_favorite for item in group_records):
            continue
        if not _match_group_query(group_records, q or ""):
            continue
        summaries.append(_build_group_summary(group_key, group_records))

    summaries.sort(key=lambda item: item["created_at"] or "", reverse=True)
    offset = (page - 1) * size
    page_items = summaries[offset:offset + size]

    return {
        "items": [AudioGroupSummaryOut.model_validate(item) for item in page_items],
        "total": len(summaries),
        "page": page,
        "size": size,
    }


@router.get("/groups/{group_id}", response_model=AudioGroupDetailOut)
async def get_audio_group_detail(group_id: str, db: AsyncSession = Depends(get_db)):
    records = await _load_group_records(group_id, db)
    if not records:
        raise HTTPException(status_code=404, detail="音频分组不存在")

    summary = _build_group_summary(group_id, records)

    # 查询该分组的合并文件
    merged_result = await db.execute(
        select(AudioRecord)
        .where(AudioRecord.source_group_id == group_id)
        .where(AudioRecord.is_merged == True)
        .order_by(AudioRecord.created_at.desc())
        .limit(1)
    )
    merged_record = merged_result.scalar_one_or_none()

    return AudioGroupDetailOut.model_validate({
        **summary,
        "has_merged": merged_record is not None,
        "records": _sort_group_records(records),
        "merged_record": merged_record,
    })


@router.delete("/groups/{group_id}")
async def delete_audio_group(group_id: str, db: AsyncSession = Depends(get_db)):
    records = await _load_group_records(group_id, db)
    if not records:
        raise HTTPException(status_code=404, detail="音频分组不存在")

    task_ids = {record.task_id for record in records if record.task_id}
    for task_id in task_ids:
        if synthesis_service.is_running(task_id):
            raise HTTPException(status_code=409, detail="任务运行中，请先取消")

    record_ids = [record.id for record in records]
    for record in records:
        full_path = get_audio_full_path(record.file_path)
        if os.path.exists(full_path):
            try:
                delete_audio_file(record.file_path)
            except OSError as e:
                logger.warning(f"删除音频文件失败 {record.file_path}: {e}")
        await db.delete(record)

    playlist_track_result = await db.execute(
        select(PlaylistTrack).where(PlaylistTrack.audio_id.in_(record_ids))
    )
    for playlist_track in playlist_track_result.scalars().all():
        await db.delete(playlist_track)

    if task_ids:
        task_result = await db.execute(select(SynthesisTask).where(SynthesisTask.task_id.in_(task_ids)))
        for task in task_result.scalars().all():
            chunk_result = await db.execute(select(SynthesisChunk).where(SynthesisChunk.task_id == task.task_id))
            for chunk in chunk_result.scalars().all():
                await db.delete(chunk)
            await db.delete(task)

    await db.commit()
    return {"message": "音频分组已删除", "deleted_records": len(records)}


@router.post("/groups/{group_id}/merge")
async def merge_audio_group(group_id: str, db: AsyncSession = Depends(get_db)):
    records = await _load_group_records(group_id, db)
    if not records:
        raise HTTPException(status_code=404, detail="音频分组不存在")
    if len(records) < 2:
        raise HTTPException(status_code=400, detail="单条音频无需合并")
    if merge_service.is_merging(group_id):
        raise HTTPException(status_code=409, detail="该分组正在合并中")

    merge_id = await merge_service.start_merge(group_id, records)
    return {"merge_id": merge_id, "group_id": group_id, "total_chunks": len(records)}


@router.get("/groups/{group_id}/merge-events/{merge_id}")
async def merge_events(group_id: str, merge_id: str):
    async def event_generator():
        queue = merge_service.subscribe(merge_id)
        try:
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event, default=str)}\n\n"
                if event.get("type") in ("merge_done", "merge_error"):
                    break
        except asyncio.CancelledError:
            pass
        finally:
            merge_service.unsubscribe(merge_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.delete("/groups/{group_id}/merge")
async def delete_merged_audio(group_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AudioRecord)
        .where(AudioRecord.source_group_id == group_id)
        .where(AudioRecord.is_merged == True)
    )
    merged_records = result.scalars().all()
    if not merged_records:
        raise HTTPException(status_code=404, detail="没有找到合并文件")

    deleted = 0
    for record in merged_records:
        full_path = get_audio_full_path(record.file_path)
        if os.path.exists(full_path):
            try:
                delete_audio_file(record.file_path)
            except OSError as e:
                logger.warning(f"删除合并文件失败 {record.file_path}: {e}")
        await db.delete(record)
        deleted += 1

    await db.commit()
    return {"message": "合并文件已删除", "deleted": deleted}
