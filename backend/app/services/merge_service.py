import asyncio
import logging
import os
import tempfile
import uuid

from app.database import async_session
from app.db_models import AudioRecord
from app.services.audio_storage import build_relative_audio_path, get_audio_full_path

logger = logging.getLogger("tingshu.merge")

# 合并任务注册表
_running_merges: dict[str, asyncio.Task] = {}
# 分组 -> merge_id 映射，防止同一分组重复合并
_group_merge_ids: dict[str, str] = {}
# 内存事件总线
_merge_events: dict[str, list[asyncio.Queue]] = {}


def subscribe(merge_id: str) -> asyncio.Queue:
    q = asyncio.Queue()
    _merge_events.setdefault(merge_id, []).append(q)
    return q


def unsubscribe(merge_id: str, q: asyncio.Queue):
    if merge_id in _merge_events:
        try:
            _merge_events[merge_id].remove(q)
        except ValueError:
            pass
        if not _merge_events[merge_id]:
            del _merge_events[merge_id]


async def emit(merge_id: str, event: dict):
    for q in _merge_events.get(merge_id, []):
        try:
            await q.put(event)
        except Exception:
            pass


def is_merging(group_id: str) -> bool:
    return group_id in _group_merge_ids


async def start_merge(group_id: str, records: list[AudioRecord]) -> str:
    merge_id = str(uuid.uuid4())
    _group_merge_ids[group_id] = merge_id

    task = asyncio.create_task(_process_merge(merge_id, group_id, records))
    _running_merges[merge_id] = task

    def _cleanup(t):
        _running_merges.pop(merge_id, None)
        _group_merge_ids.pop(group_id, None)

    task.add_done_callback(_cleanup)
    return merge_id


async def _process_merge(merge_id: str, group_id: str, records: list[AudioRecord]):
    total = len(records)
    await emit(merge_id, {"type": "merge_started", "total_chunks": total})

    try:
        # 1. 验证源文件
        source_paths = []
        for i, record in enumerate(records):
            full_path = get_audio_full_path(record.file_path)
            if not os.path.exists(full_path):
                await emit(merge_id, {
                    "type": "merge_error",
                    "error": f"文件缺失: {record.title} (chunk {record.chunk_index})",
                })
                return
            source_paths.append(full_path)
            await emit(merge_id, {
                "type": "merge_progress",
                "step": "preparing",
                "current": i + 1,
                "total": total,
            })

        # 2. 写 ffmpeg concat 文件列表
        fd, list_path = tempfile.mkstemp(suffix=".txt", prefix="merge_")
        try:
            with os.fdopen(fd, "w") as f:
                for path in source_paths:
                    # 转义单引号
                    escaped = path.replace("'", "'\\''")
                    f.write(f"file '{escaped}'\n")

            # 3. 生成输出路径
            relative_path = build_relative_audio_path(extension="wav")
            output_path = get_audio_full_path(relative_path)
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            await emit(merge_id, {"type": "merge_progress", "step": "merging", "current": 0, "total": 1})

            # 4. 执行 ffmpeg
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", output_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                error_msg = stderr.decode(errors="replace").strip().split("\n")[-1]
                await emit(merge_id, {"type": "merge_error", "error": f"ffmpeg 失败: {error_msg}"})
                return
        finally:
            # 清理临时文件
            try:
                os.unlink(list_path)
            except OSError:
                pass

        # 5. 计算文件信息
        file_size = os.path.getsize(output_path)
        duration = file_size / (24000 * 2)  # 与合成服务一致：16bit mono 24kHz

        await emit(merge_id, {"type": "merge_progress", "step": "saving", "current": 1, "total": 1})

        # 6. 创建数据库记录
        merged_text = "\n".join(r.text_content for r in records)
        async with async_session() as db:
            record = AudioRecord(
                title=f"{records[0].title} (合并)" if records[0].title else "合并音频",
                text_content=merged_text,
                voice_name=records[0].voice_name,
                voice_id=records[0].voice_id,
                model=records[0].model,
                styles=records[0].styles,
                file_path=relative_path,
                file_size=file_size,
                duration=duration,
                is_merged=True,
                source_group_id=group_id,
                group_id=None,
                chunk_index=0,
                task_id=None,
            )
            db.add(record)
            await db.commit()
            await db.refresh(record)

        await emit(merge_id, {
            "type": "merge_done",
            "merge_id": merge_id,
            "record_id": record.id,
            "duration": round(duration, 2),
            "file_size": file_size,
        })
        logger.info(f"合并完成: group={group_id}, record_id={record.id}, duration={duration:.1f}s")

    except Exception as e:
        logger.exception(f"合并失败: group={group_id}")
        await emit(merge_id, {"type": "merge_error", "error": str(e)})
