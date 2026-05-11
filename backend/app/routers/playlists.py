from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import PlaylistCreate, PlaylistOut, PlaylistTrackAdd, PlaylistTrackOut
from app.db_models import Playlist, PlaylistTrack, AudioRecord

router = APIRouter()


@router.get("", response_model=list[PlaylistOut])
async def get_playlists(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Playlist).order_by(Playlist.created_at.desc()))
    return result.scalars().all()


@router.post("", response_model=PlaylistOut)
async def create_playlist(req: PlaylistCreate, db: AsyncSession = Depends(get_db)):
    playlist = Playlist(name=req.name, description=req.description)
    db.add(playlist)
    await db.commit()
    await db.refresh(playlist)
    return playlist


@router.put("/{playlist_id}", response_model=PlaylistOut)
async def update_playlist(playlist_id: int, req: PlaylistCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Playlist).where(Playlist.id == playlist_id))
    playlist = result.scalar_one_or_none()
    if not playlist:
        raise HTTPException(status_code=404, detail="播放列表不存在")
    playlist.name = req.name
    playlist.description = req.description
    await db.commit()
    await db.refresh(playlist)
    return playlist


@router.delete("/{playlist_id}")
async def delete_playlist(playlist_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Playlist).where(Playlist.id == playlist_id))
    playlist = result.scalar_one_or_none()
    if not playlist:
        raise HTTPException(status_code=404, detail="播放列表不存在")
    await db.delete(playlist)
    await db.commit()
    return {"message": "已删除"}


@router.post("/{playlist_id}/tracks")
async def add_track(playlist_id: int, req: PlaylistTrackAdd, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Playlist).where(Playlist.id == playlist_id))
    playlist = result.scalar_one_or_none()
    if not playlist:
        raise HTTPException(status_code=404, detail="播放列表不存在")

    result = await db.execute(select(AudioRecord).where(AudioRecord.id == req.audio_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="音频记录不存在")

    result = await db.execute(
        select(PlaylistTrack)
        .where(PlaylistTrack.playlist_id == playlist_id)
        .order_by(PlaylistTrack.sort_order.desc())
    )
    last = result.scalars().first()
    sort_order = (last.sort_order + 1) if last else 0

    track = PlaylistTrack(playlist_id=playlist_id, audio_id=req.audio_id, sort_order=sort_order)
    db.add(track)
    await db.commit()
    return {"message": "已添加"}


@router.delete("/{playlist_id}/tracks/{track_id}")
async def remove_track(playlist_id: int, track_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PlaylistTrack).where(
            PlaylistTrack.id == track_id,
            PlaylistTrack.playlist_id == playlist_id,
        )
    )
    track = result.scalar_one_or_none()
    if not track:
        raise HTTPException(status_code=404, detail="曲目不存在")
    await db.delete(track)
    await db.commit()
    return {"message": "已移除"}


@router.get("/{playlist_id}/tracks", response_model=list[PlaylistTrackOut])
async def get_tracks(playlist_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PlaylistTrack, AudioRecord)
        .join(AudioRecord, PlaylistTrack.audio_id == AudioRecord.id)
        .where(PlaylistTrack.playlist_id == playlist_id)
        .order_by(PlaylistTrack.sort_order)
    )
    return [
        {
            "track_id": track.id,
            "sort_order": track.sort_order,
            "audio": audio,
        }
        for track, audio in result.all()
    ]
