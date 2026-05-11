import io
import json
import logging
import wave
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import SynthesizeRequest, SynthesizeLongRequest, AudioRecordOut
from app.db_models import AudioRecord, CustomVoice, Setting
from app.services.audio_storage import write_audio_file
from app.services.mimo_tts import synthesize_preset, synthesize_design, synthesize_clone
from app.services.text_service import split_text
from app.config import settings

logger = logging.getLogger("tingshu.tts")


def get_wav_duration(audio_bytes: bytes) -> float:
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        return 0.0

router = APIRouter()


async def get_api_key(db: AsyncSession) -> str:
    result = await db.execute(select(Setting).where(Setting.key == "mimo_api_key"))
    row = result.scalar_one_or_none()
    return row.value if row else settings.mimo_api_key


async def get_setting(db: AsyncSession, key: str, default: str = "") -> str:
    result = await db.execute(select(Setting).where(Setting.key == key))
    row = result.scalar_one_or_none()
    return row.value if row else default


async def resolve_voice(db: AsyncSession, voice_id: int | None, voice: str, api_key: str, text: str, styles: list[str], model: str = None, base_url: str = None):
    """根据 voice_id 或 voice 名称解析并调用对应的 TTS 方法"""
    if voice_id:
        result = await db.execute(select(CustomVoice).where(CustomVoice.id == voice_id))
        custom_voice = result.scalar_one_or_none()
        if not custom_voice:
            raise HTTPException(status_code=404, detail="自定义音色不存在")
        voice_name = custom_voice.name
        if custom_voice.type == "design":
            audio_bytes = await synthesize_design(api_key, custom_voice.description, text, styles, base_url=base_url)
        else:
            audio_bytes = await synthesize_clone(api_key, custom_voice.sample_path, text, styles, base_url=base_url)
    else:
        voice_name = voice or "mimo_default"
        audio_bytes = await synthesize_preset(api_key, voice_name, text, styles, model, base_url=base_url)
    return voice_name, audio_bytes


async def save_audio_file(audio_bytes: bytes) -> tuple[str, str]:
    """保存音频文件，返回 (file_path, full_path)"""
    return await write_audio_file(audio_bytes, extension="wav")


@router.post("/synthesize", response_model=AudioRecordOut)
async def synthesize(req: SynthesizeRequest, db: AsyncSession = Depends(get_db)):
    api_key = await get_api_key(db)
    base_url = await get_setting(db, "mimo_base_url", settings.mimo_base_url)
    voice_name, audio_bytes = await resolve_voice(db, req.voice_id, req.voice, api_key, req.text, req.styles, req.model, base_url)

    file_path, _ = await save_audio_file(audio_bytes)

    title = req.text[:20] + ("..." if len(req.text) > 20 else "")
    duration = get_wav_duration(audio_bytes)
    record = AudioRecord(
        title=title,
        text_content=req.text,
        voice_name=voice_name,
        voice_id=req.voice_id,
        model=req.model,
        styles=json.dumps(req.styles),
        file_path=file_path,
        file_size=len(audio_bytes),
        duration=duration,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


@router.post("/synthesize-long")
async def synthesize_long(req: SynthesizeLongRequest, db: AsyncSession = Depends(get_db)):
    api_key = await get_api_key(db)
    base_url = await get_setting(db, "mimo_base_url", settings.mimo_base_url)
    chunks = split_text(req.text, req.chunk_size)
    group_id = str(uuid.uuid4())

    async def event_generator():
        yield f"data: {json.dumps({'total': len(chunks)})}\n\n"
        record_ids = []
        for i, chunk in enumerate(chunks):
            try:
                voice_name, audio_bytes = await resolve_voice(
                    db, req.voice_id, req.voice, api_key, chunk, req.styles, req.model, base_url
                )
            except Exception as e:
                logger.error(f"合成第 {i+1} 段失败: {e}")
                yield f"data: {json.dumps({'segment': i + 1, 'error': f'第 {i+1} 段合成失败: {str(e)}'})}\n\n"
                record_ids.append(None)
                continue

            file_path, _ = await save_audio_file(audio_bytes)

            title = chunk[:20] + ("..." if len(chunk) > 20 else "")
            duration = get_wav_duration(audio_bytes)
            record = AudioRecord(
                title=title,
                text_content=chunk,
                voice_name=voice_name,
                voice_id=req.voice_id,
                model=req.model,
                styles=json.dumps(req.styles),
                file_path=file_path,
                file_size=len(audio_bytes),
                duration=duration,
                group_id=group_id,
                chunk_index=i,
            )
            db.add(record)
            await db.commit()
            await db.refresh(record)
            record_ids.append(record.id)

            yield f"data: {json.dumps({'segment': i + 1, 'progress': i + 1, 'record_id': record.id})}\n\n"

        valid_ids = [rid for rid in record_ids if rid is not None]
        yield f"data: {json.dumps({'done': True, 'group_id': group_id, 'record_ids': valid_ids})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/preview")
async def preview(req: SynthesizeRequest, db: AsyncSession = Depends(get_db)):
    api_key = await get_api_key(db)
    base_url = await get_setting(db, "mimo_base_url", settings.mimo_base_url)
    preview_text = req.text[:100]
    _, audio_bytes = await resolve_voice(db, req.voice_id, req.voice, api_key, preview_text, req.styles, req.model, base_url)
    return Response(content=audio_bytes, media_type="audio/wav")
