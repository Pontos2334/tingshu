from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.database import get_db
from app.db_models import Setting
from app.config import settings

router = APIRouter()


def mask_key(key: str) -> str:
    if not key or len(key) < 8:
        return "****"
    return key[:4] + "****"


class SettingsUpdate(BaseModel):
    mimo_api_key: str | None = None
    default_voice: str | None = None
    mimo_base_url: str | None = None
    mimo_model: str | None = None
    deepseek_api_key: str | None = None
    deepseek_base_url: str | None = None
    deepseek_model: str | None = None
    whisper_api_key: str | None = None
    whisper_api_base_url: str | None = None
    xunfei_appid: str | None = None
    xunfei_api_key: str | None = None
    xunfei_api_secret: str | None = None
    subtitle_asr_engine: str | None = None
    subtitle_faster_whisper_model: str | None = None
    subtitle_whisper_api_model: str | None = None
    subtitle_target_language: str | None = None


_SECRET_FIELDS = {"mimo_api_key", "deepseek_api_key", "whisper_api_key", "xunfei_api_key", "xunfei_api_secret"}


@router.get("")
async def get_settings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Setting))
    rows = result.scalars().all()
    config = {row.key: row.value for row in rows}

    # Mask secret fields and add *_set flags
    defaults = {
        "mimo_api_key": settings.mimo_api_key,
        "deepseek_api_key": settings.deepseek_api_key,
        "whisper_api_key": settings.whisper_api_key,
        "xunfei_api_key": settings.xunfei_api_key,
        "xunfei_api_secret": settings.xunfei_api_secret,
    }
    for key, default_val in defaults.items():
        actual = config.get(key, default_val)
        config[key] = mask_key(actual)
        config[f"{key}_set"] = bool(actual)

    config.setdefault("default_voice", "冰糖")
    config.setdefault("whisper_api_base_url", settings.whisper_api_base_url)
    config.setdefault("xunfei_appid", settings.xunfei_appid)
    config.setdefault("subtitle_asr_engine", "whisper")
    config.setdefault("subtitle_faster_whisper_model", "base")
    config.setdefault("subtitle_whisper_api_model", "whisper-1")
    config.setdefault("subtitle_target_language", "简体中文")
    return config


@router.put("")
async def update_settings(data: SettingsUpdate, db: AsyncSession = Depends(get_db)):
    update_data = data.model_dump(exclude_none=True)
    for key, value in update_data.items():
        result = await db.execute(select(Setting).where(Setting.key == key))
        row = result.scalar_one_or_none()
        if row:
            row.value = str(value)
        else:
            db.add(Setting(key=key, value=str(value)))
    await db.commit()
    return {"message": "设置已保存"}
