import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import Base
from app.db_models import AudioRecord, Playlist, PlaylistTrack
from app.routers.audio import get_audio_group_detail, get_audio_groups
from app.routers.playlists import get_tracks


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_audio_groups_merge_long_text_records_and_single_records(db_session):
    db_session.add_all([
        AudioRecord(
            title="唐末故事",
            text_content="第一段",
            voice_name="冰糖",
            styles="[]",
            file_path="20260510/a.wav",
            duration=12.5,
            group_id="group-1",
            chunk_index=0,
        ),
        AudioRecord(
            title="唐末故事",
            text_content="第二段",
            voice_name="冰糖",
            styles="[]",
            file_path="20260510/b.wav",
            duration=7.5,
            is_favorite=True,
            group_id="group-1",
            chunk_index=1,
        ),
        AudioRecord(
            title="单条合成",
            text_content="单条内容",
            voice_name="白桦",
            styles="[]",
            file_path="20260510/c.wav",
            duration=4,
        ),
    ])
    await db_session.commit()

    result = await get_audio_groups(page=1, size=20, q=None, favorite=None, db=db_session)

    assert result["total"] == 2
    summary_map = {item.group_id: item for item in result["items"]}

    assert "group-1" in summary_map
    assert "record-3" in summary_map
    assert summary_map["group-1"].clip_count == 2
    assert summary_map["group-1"].total_duration == 20.0
    assert summary_map["group-1"].has_favorite is True
    assert summary_map["group-1"].source_type == "long_text"

    detail = await get_audio_group_detail("group-1", db=db_session)
    assert detail.clip_count == 2
    assert [record.chunk_index for record in detail.records] == [0, 1]


@pytest.mark.asyncio
async def test_playlist_tracks_return_track_contract(db_session):
    audio = AudioRecord(
        title="播放片段",
        text_content="播放内容",
        voice_name="冰糖",
        styles="[]",
        file_path="20260510/play.wav",
        duration=10,
    )
    playlist = Playlist(name="我的列表", description="测试列表")
    db_session.add_all([audio, playlist])
    await db_session.flush()

    track = PlaylistTrack(playlist_id=playlist.id, audio_id=audio.id, sort_order=0)
    db_session.add(track)
    await db_session.commit()

    items = await get_tracks(playlist.id, db=db_session)

    assert len(items) == 1
    assert items[0]["track_id"] == track.id
    assert items[0]["sort_order"] == 0
    assert items[0]["audio"].id == audio.id
