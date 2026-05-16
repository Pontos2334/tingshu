import os
import uuid
from datetime import datetime

import aiofiles

from app.config import settings


def _backend_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _resolve_storage_root(config_path: str) -> str:
    if os.path.isabs(config_path):
        return config_path
    return os.path.abspath(os.path.join(_backend_root(), config_path))


def get_video_storage_root() -> str:
    return _resolve_storage_root(settings.video_storage_path)


def get_subtitle_storage_root() -> str:
    return _resolve_storage_root(settings.subtitle_storage_path)


def build_relative_video_path(filename: str, now: datetime | None = None) -> str:
    timestamp = now or datetime.now()
    date_dir = timestamp.strftime("%Y%m%d")
    ext = os.path.splitext(filename)[1] or ".mp4"
    return f"{date_dir}/{uuid.uuid4()}{ext}"


def build_relative_subtitle_path(extension: str = "srt", now: datetime | None = None) -> str:
    timestamp = now or datetime.now()
    date_dir = timestamp.strftime("%Y%m%d")
    return f"{date_dir}/{uuid.uuid4()}.{extension.lstrip('.')}"


def get_video_full_path(file_path: str) -> str:
    normalized = os.path.normpath(file_path)
    if os.path.isabs(normalized):
        return normalized
    return os.path.join(get_video_storage_root(), normalized)


def get_subtitle_full_path(file_path: str) -> str:
    normalized = os.path.normpath(file_path)
    if os.path.isabs(normalized):
        return normalized
    return os.path.join(get_subtitle_storage_root(), normalized)


async def write_video_file(filename: str, content: bytes) -> tuple[str, str]:
    relative_path = build_relative_video_path(filename)
    full_path = get_video_full_path(relative_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    async with aiofiles.open(full_path, "wb") as f:
        await f.write(content)
    return relative_path, full_path


async def write_video_stream(filename: str, file_obj, max_bytes: int) -> tuple[str, int]:
    """Stream-upload a video file, writing in 1MB chunks. Raises ValueError if too large."""
    relative_path = build_relative_video_path(filename)
    full_path = get_video_full_path(relative_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    chunk_size = 1024 * 1024
    total = 0
    async with aiofiles.open(full_path, "wb") as f:
        while True:
            chunk = await file_obj.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                await f.close()
                os.remove(full_path)
                raise ValueError(f"文件过大，最大 {max_bytes // (1024*1024)}MB")
            await f.write(chunk)
    return relative_path, total


async def write_audio_stream(filename: str, file_obj, max_bytes: int) -> tuple[str, int]:
    """Stream-upload an audio file to subtitle storage. Raises ValueError if too large."""
    ext = os.path.splitext(filename)[1] or ".wav"
    relative_path = build_relative_subtitle_path(ext)
    full_path = get_subtitle_full_path(relative_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    chunk_size = 1024 * 1024
    total = 0
    async with aiofiles.open(full_path, "wb") as f:
        while True:
            chunk = await file_obj.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                await f.close()
                os.remove(full_path)
                raise ValueError(f"文件过大，最大 {max_bytes // (1024*1024)}MB")
            await f.write(chunk)
    return relative_path, total


async def write_subtitle_file(content: str, extension: str = "srt") -> tuple[str, str]:
    relative_path = build_relative_subtitle_path(extension)
    full_path = get_subtitle_full_path(relative_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    async with aiofiles.open(full_path, "w", encoding="utf-8") as f:
        await f.write(content)
    return relative_path, full_path


def delete_file(file_path: str, file_type: str = "video") -> bool:
    if file_type == "video":
        full_path = get_video_full_path(file_path)
    else:
        full_path = get_subtitle_full_path(file_path)
    if not os.path.exists(full_path):
        return False
    os.remove(full_path)
    return True
