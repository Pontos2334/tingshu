import os
import uuid
import logging

import aiofiles
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import VoiceDesignRequest, VoiceOut
from app.db_models import CustomVoice, Setting
from app.services.mimo_tts import synthesize_design, synthesize_clone
from app.config import settings

logger = logging.getLogger("tingshu.voices")

router = APIRouter()

PRESET_VOICES = [
    {"name": "冰糖", "language": "中文", "gender": "女性"},
    {"name": "茉莉", "language": "中文", "gender": "女性"},
    {"name": "苏打", "language": "中文", "gender": "男性"},
    {"name": "白桦", "language": "中文", "gender": "男性"},
    {"name": "Mia", "language": "英文", "gender": "女性"},
    {"name": "Chloe", "language": "英文", "gender": "女性"},
    {"name": "Milo", "language": "英文", "gender": "男性"},
    {"name": "Dean", "language": "英文", "gender": "男性"},
]

ALLOWED_UPLOAD_TYPES = {"audio/wav", "audio/mpeg", "audio/mp3", "audio/x-wav", "audio/x-mpeg"}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB


async def get_api_key(db: AsyncSession) -> str:
    result = await db.execute(select(Setting).where(Setting.key == "mimo_api_key"))
    row = result.scalar_one_or_none()
    return row.value if row else settings.mimo_api_key


async def get_setting(db: AsyncSession, key: str, default: str = "") -> str:
    result = await db.execute(select(Setting).where(Setting.key == key))
    row = result.scalar_one_or_none()
    return row.value if row else default


@router.get("/presets")
async def get_presets():
    return PRESET_VOICES


@router.get("/custom", response_model=list[VoiceOut])
async def get_custom_voices(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CustomVoice).order_by(CustomVoice.created_at.desc()))
    return result.scalars().all()


@router.post("/design", response_model=VoiceOut)
async def design_voice(req: VoiceDesignRequest, db: AsyncSession = Depends(get_db)):
    api_key = await get_api_key(db)
    base_url = await get_setting(db, "mimo_base_url", settings.mimo_base_url)
    sample_text = req.sample_text or "你好，欢迎来到我的听书世界。"
    audio_bytes = await synthesize_design(api_key, req.description, sample_text, base_url=base_url)

    file_id = str(uuid.uuid4())
    file_path = os.path.join(settings.sample_storage_path, f"{file_id}.wav")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(audio_bytes)

    voice = CustomVoice(
        name=req.name,
        type="design",
        description=req.description,
        preview_path=file_path,
        model="mimo-v2.5-tts-voicedesign",
    )
    db.add(voice)
    await db.commit()
    await db.refresh(voice)
    return voice


@router.post("/clone", response_model=VoiceOut)
async def clone_voice(
    file: UploadFile = File(...),
    name: str = Form(...),
    sample_text: str = Form("你好，欢迎来到我的听书世界。"),
    db: AsyncSession = Depends(get_db),
):
    # 验证文件类型
    if file.content_type and file.content_type not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(status_code=400, detail="仅支持 wav/mp3 格式的音频文件")

    # 验证文件大小
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="文件大小不能超过 10MB")

    api_key = await get_api_key(db)
    base_url = await get_setting(db, "mimo_base_url", settings.mimo_base_url)

    file_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1] if file.filename else ".wav"
    if ext.lower() not in {".wav", ".mp3"}:
        ext = ".wav"
    sample_path = os.path.join(settings.sample_storage_path, f"{file_id}{ext}")
    os.makedirs(os.path.dirname(sample_path), exist_ok=True)
    async with aiofiles.open(sample_path, "wb") as f:
        await f.write(content)

    audio_bytes = await synthesize_clone(api_key, sample_path, sample_text, base_url=base_url)
    preview_path = os.path.join(settings.sample_storage_path, f"{file_id}_preview.wav")
    async with aiofiles.open(preview_path, "wb") as f:
        await f.write(audio_bytes)

    voice = CustomVoice(
        name=name,
        type="clone",
        sample_path=sample_path,
        preview_path=preview_path,
        model="mimo-v2.5-tts-voiceclone",
    )
    db.add(voice)
    await db.commit()
    await db.refresh(voice)
    return voice


@router.delete("/custom/{voice_id}")
async def delete_custom_voice(voice_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CustomVoice).where(CustomVoice.id == voice_id))
    voice = result.scalar_one_or_none()
    if not voice:
        raise HTTPException(status_code=404, detail="音色不存在")

    for path in [voice.sample_path, voice.preview_path]:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError as e:
                logger.warning(f"删除文件失败 {path}: {e}")

    await db.delete(voice)
    await db.commit()
    return {"message": "已删除"}


@router.get("/custom/{voice_id}", response_model=VoiceOut)
async def get_custom_voice(voice_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CustomVoice).where(CustomVoice.id == voice_id))
    voice = result.scalar_one_or_none()
    if not voice:
        raise HTTPException(status_code=404, detail="音色不存在")
    return voice


@router.get("/preview/{voice_id}")
async def get_voice_preview(voice_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CustomVoice).where(CustomVoice.id == voice_id))
    voice = result.scalar_one_or_none()
    if not voice or not voice.preview_path:
        raise HTTPException(status_code=404, detail="预览音频不存在")
    if not os.path.exists(voice.preview_path):
        raise HTTPException(status_code=404, detail="预览音频文件不存在")
    return FileResponse(voice.preview_path, media_type="audio/wav")
