from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 迁移：添加后增的列（SQLite 不支持 IF NOT EXISTS ALTER TABLE）
        migrations = [
            ("audio_records", "is_merged", "BOOLEAN DEFAULT 0"),
            ("audio_records", "source_group_id", "VARCHAR"),
        ]
        for table, column, col_type in migrations:
            try:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
            except Exception:
                pass  # 列已存在


async def get_db():
    async with async_session() as session:
        yield session
