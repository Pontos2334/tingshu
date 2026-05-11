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


@router.get("")
async def get_settings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Setting))
    rows = result.scalars().all()
    config = {row.key: row.value for row in rows}
    api_key = config.get("mimo_api_key", settings.mimo_api_key)
    config["mimo_api_key"] = mask_key(api_key)
    config["mimo_api_key_set"] = bool(api_key)
    deepseek_key = config.get("deepseek_api_key", settings.deepseek_api_key)
    config["deepseek_api_key"] = mask_key(deepseek_key)
    config["deepseek_api_key_set"] = bool(deepseek_key)
    config.setdefault("default_voice", "冰糖")
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
