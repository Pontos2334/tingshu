import os
import uuid
from datetime import datetime

import aiofiles

from app.config import settings


def _backend_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def get_audio_storage_root() -> str:
    storage_path = settings.audio_storage_path
    if os.path.isabs(storage_path):
        return storage_path
    return os.path.abspath(os.path.join(_backend_root(), storage_path))


def build_relative_audio_path(extension: str = "wav", now: datetime | None = None) -> str:
    timestamp = now or datetime.now()
    date_dir = timestamp.strftime("%Y%m%d")
    return f"{date_dir}/{uuid.uuid4()}.{extension.lstrip('.')}"


def get_audio_full_path(file_path: str) -> str:
    normalized_path = os.path.normpath(file_path)
    if os.path.isabs(normalized_path):
        return normalized_path

    normalized_storage = os.path.normpath(settings.audio_storage_path)
    if normalized_path.startswith(normalized_storage):
        return os.path.abspath(os.path.join(_backend_root(), normalized_path))

    return os.path.join(get_audio_storage_root(), normalized_path)


async def write_audio_file(audio_bytes: bytes, extension: str = "wav") -> tuple[str, str]:
    relative_path = build_relative_audio_path(extension=extension)
    full_path = get_audio_full_path(relative_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    async with aiofiles.open(full_path, "wb") as f:
        await f.write(audio_bytes)
    return relative_path, full_path


def delete_audio_file(file_path: str) -> bool:
    full_path = get_audio_full_path(file_path)
    if not os.path.exists(full_path):
        return False
    os.remove(full_path)
    return True
