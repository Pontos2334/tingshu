import asyncio
import json
import logging
from datetime import datetime, timezone

from app.database import async_session
from app.db_models import SynthesisTask, SynthesisChunk, AudioRecord
from app.services.audio_storage import write_audio_file
from app.services.mimo_tts import synthesize_preset, synthesize_design, synthesize_clone

logger = logging.getLogger("tingshu.synthesis")

# 任务注册表：防止同一 task_id 被重复启动
_running_tasks: dict[str, asyncio.Task] = {}

# 任务取消标志
_cancel_flags: dict[str, bool] = {}

# 内存事件总线（通知层，非状态源）
_task_events: dict[str, list[asyncio.Queue]] = {}

# DB 写入锁（细粒度，仅保护 commit 操作）
_db_lock = asyncio.Lock()


def subscribe(task_id: str) -> asyncio.Queue:
    q = asyncio.Queue()
    _task_events.setdefault(task_id, []).append(q)
    return q


def unsubscribe(task_id: str, q: asyncio.Queue):
    if task_id in _task_events:
        try:
            _task_events[task_id].remove(q)
        except ValueError:
            pass
        if not _task_events[task_id]:
            del _task_events[task_id]


async def emit(task_id: str, event: dict):
    for q in _task_events.get(task_id, []):
        try:
            await q.put(event)
        except Exception:
            pass


def is_running(task_id: str) -> bool:
    return task_id in _running_tasks


def cancel_task(task_id: str):
    _cancel_flags[task_id] = True
    task = _running_tasks.get(task_id)
    if task and not task.done():
        task.cancel()


def is_cancel_requested(task_id: str) -> bool:
    return _cancel_flags.get(task_id, False)


async def resolve_voice(db, voice_name: str, voice_id: int, styles: list[str], text: str, api_key: str, base_url: str, model: str) -> tuple[bytes, str]:
    """解析音色并合成音频，返回 (audio_bytes, resolved_voice_name)"""
    if voice_id:
        from sqlalchemy import select
        from app.db_models import CustomVoice
        result = await db.execute(select(CustomVoice).where(CustomVoice.id == voice_id))
        custom = result.scalar_one_or_none()
        if not custom:
            raise ValueError(f"自定义音色不存在: {voice_id}")
        if custom.type == "design":
            audio = await synthesize_design(api_key, custom.description, text, styles, base_url)
        else:
            audio = await synthesize_clone(api_key, custom.sample_path, text, styles, base_url)
        return audio, custom.name
    else:
        voice = voice_name or "冰糖"
        audio = await synthesize_preset(api_key, voice, text, styles, model, base_url)
        return audio, voice


def start_task(task_id: str):
    """启动后台合成任务（如果未在运行）"""
    if task_id in _running_tasks:
        return
    _cancel_flags[task_id] = False
    task = asyncio.create_task(process_synthesis_task(task_id))
    _running_tasks[task_id] = task
    task.add_done_callback(lambda t: _cleanup_task(task_id))


def _cleanup_task(task_id: str):
    _running_tasks.pop(task_id, None)
    _cancel_flags.pop(task_id, None)


async def process_synthesis_task(task_id: str):
    """后台处理合成任务"""
    logger.info(f"开始处理合成任务: {task_id}")

    async with async_session() as db:
        from sqlalchemy import select

        # 读取任务信息
        result = await db.execute(select(SynthesisTask).where(SynthesisTask.task_id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            logger.error(f"任务不存在: {task_id}")
            return

        # 更新任务状态为 running
        task.status = "running"
        async with _db_lock:
            await db.commit()

        await emit(task_id, {"type": "task_started", "task_id": task_id})

        # 获取 API 配置
        from app.config import settings
        from app.db_models import Setting
        result = await db.execute(select(Setting).where(Setting.key == "mimo_api_key"))
        row = result.scalar_one_or_none()
        api_key = row.value if row else settings.mimo_api_key
        base_url = settings.mimo_base_url

        if not api_key:
            task.status = "failed"
            async with _db_lock:
                await db.commit()
            await emit(task_id, {"type": "task_error", "error": "未配置 API Key"})
            return

        # 解析 styles
        styles = json.loads(task.styles) if task.styles else []

        # 获取待处理的 chunks（pending 或 failed）
        result = await db.execute(
            select(SynthesisChunk)
            .where(SynthesisChunk.task_id == task_id)
            .where(SynthesisChunk.status.in_(["pending", "failed"]))
            .order_by(SynthesisChunk.chunk_index)
        )
        chunks_to_process = result.scalars().all()

        for chunk in chunks_to_process:
            # 检查取消标志
            if is_cancel_requested(task_id):
                task.status = "canceled"
                async with _db_lock:
                    await db.commit()
                await emit(task_id, {"type": "task_canceled"})
                logger.info(f"任务已取消: {task_id}")
                return

            # 标记 chunk 为 running
            chunk.status = "running"
            chunk.error_message = None
            async with _db_lock:
                await db.commit()

            await emit(task_id, {
                "type": "chunk_started",
                "chunk_index": chunk.chunk_index,
            })

            # 合成（带重试）
            max_retries = 3
            success = False
            last_error = None
            for attempt in range(max_retries):
                try:
                    audio_bytes, voice_name = await resolve_voice(
                        db, task.voice_name, task.voice_id, styles,
                        chunk.text_content, api_key, base_url, task.model
                    )
                    success = True
                    break
                except Exception as e:
                    last_error = e
                    chunk.retry_count = attempt + 1
                    logger.warning(f"任务 {task_id} 第 {chunk.chunk_index} 段合成失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        wait = 2 ** (attempt + 1)
                        await emit(task_id, {
                            "type": "chunk_retry",
                            "chunk_index": chunk.chunk_index,
                            "attempt": attempt + 1,
                            "wait": wait,
                        })
                        await asyncio.sleep(wait)

            if not success:
                # 标记失败
                chunk.status = "failed"
                chunk.error_message = str(last_error) if last_error else "合成失败"
                task.failed_chunks += 1
                async with _db_lock:
                    await db.commit()
                await emit(task_id, {
                    "type": "chunk_failed",
                    "chunk_index": chunk.chunk_index,
                    "error": chunk.error_message,
                })
                continue

            # 保存音频文件（统一使用相对 audio_storage_path 的 file_path）
            file_path, _ = await write_audio_file(audio_bytes, extension="wav")

            # 计算时长（估算：WAV 16bit 24kHz mono）
            duration = len(audio_bytes) / (24000 * 2) if audio_bytes else 0

            # 创建 AudioRecord
            record = AudioRecord(
                title=task.title[:50] if task.title else f"长文本第{chunk.chunk_index + 1}段",
                text_content=chunk.text_content,
                voice_name=voice_name,
                voice_id=task.voice_id,
                model=task.model,
                styles=json.dumps(styles),
                file_path=file_path,
                file_size=len(audio_bytes),
                duration=duration,
                group_id=task_id,
                chunk_index=chunk.chunk_index,
                task_id=task_id,
            )
            db.add(record)

            # 更新 chunk 状态
            chunk.status = "completed"
            chunk.audio_record_id = record.id
            chunk.error_message = None
            task.completed_chunks += 1

            async with _db_lock:
                await db.commit()

            await emit(task_id, {
                "type": "chunk_done",
                "chunk_index": chunk.chunk_index,
                "record_id": record.id,
                "duration": duration,
            })

        # 更新最终任务状态
        if task.failed_chunks == 0:
            task.status = "completed"
        elif task.completed_chunks == 0:
            task.status = "failed"
        else:
            task.status = "partial"

        async with _db_lock:
            await db.commit()

        # 获取所有 record_ids
        result = await db.execute(
            select(AudioRecord.id)
            .where(AudioRecord.task_id == task_id)
            .order_by(AudioRecord.chunk_index)
        )
        record_ids = [r[0] for r in result.all()]

        await emit(task_id, {
            "type": "task_done",
            "task_id": task_id,
            "status": task.status,
            "completed": task.completed_chunks,
            "failed": task.failed_chunks,
            "record_ids": record_ids,
        })

        logger.info(f"任务完成: {task_id}, 状态={task.status}, 完成={task.completed_chunks}, 失败={task.failed_chunks}")


async def resume_task(task_id: str):
    """恢复失败/部分完成的任务：重置 failed chunks 为 pending，重新启动处理"""
    async with async_session() as db:
        from sqlalchemy import select, update

        result = await db.execute(select(SynthesisTask).where(SynthesisTask.task_id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            raise ValueError("任务不存在")
        if task.status == "running":
            raise ValueError("任务正在运行中")
        if task.status in ("completed", "canceled"):
            raise ValueError(f"任务状态为 {task.status}，无需恢复")

        # 重置 failed chunks 为 pending
        await db.execute(
            update(SynthesisChunk)
            .where(SynthesisChunk.task_id == task_id)
            .where(SynthesisChunk.status == "failed")
            .values(status="pending", error_message=None)
        )
        task.failed_chunks = 0
        task.status = "pending"
        async with _db_lock:
            await db.commit()

    start_task(task_id)


async def retry_failed_chunks(task_id: str):
    """仅重试失败的段"""
    async with async_session() as db:
        from sqlalchemy import select, update

        result = await db.execute(select(SynthesisTask).where(SynthesisTask.task_id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            raise ValueError("任务不存在")
        if task.status == "running":
            raise ValueError("任务正在运行中")

        # 重置 failed chunks 为 pending
        await db.execute(
            update(SynthesisChunk)
            .where(SynthesisChunk.task_id == task_id)
            .where(SynthesisChunk.status == "failed")
            .values(status="pending", error_message=None)
        )
        task.failed_chunks = 0
        if task.status == "failed":
            task.status = "partial"
        async with _db_lock:
            await db.commit()

    start_task(task_id)
