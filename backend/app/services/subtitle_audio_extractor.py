import asyncio
import json
import logging
import os
from typing import Callable

from app.services.subtitle_storage import get_video_full_path

logger = logging.getLogger("tingshu.subtitle.extractor")

ALLOWED_VIDEO_EXTENSIONS = {
    ".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv",
    ".webm", ".m4v", ".mpeg", ".mpg", ".ts",
}


async def check_ffmpeg() -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()
        return proc.returncode == 0
    except FileNotFoundError:
        return False


async def probe_media(file_path: str) -> dict:
    full_path = get_video_full_path(file_path) if not os.path.isabs(file_path) else file_path
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", full_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe 失败: {stderr.decode()}")
    data = json.loads(stdout)

    video_stream = next((s for s in data.get("streams", []) if s["codec_type"] == "video"), None)
    audio_stream = next((s for s in data.get("streams", []) if s["codec_type"] == "audio"), None)
    fmt = data.get("format", {})

    return {
        "duration": float(fmt.get("duration", 0)),
        "size": int(fmt.get("size", 0)),
        "has_audio": audio_stream is not None,
        "audio_codec": audio_stream.get("codec_name") if audio_stream else None,
        "video_codec": video_stream.get("codec_name") if video_stream else None,
        "resolution": f"{video_stream.get('width', 0)}x{video_stream.get('height', 0)}" if video_stream else None,
    }


async def extract_audio(
    video_path: str,
    output_path: str,
    emit_event: Callable | None = None,
) -> str:
    full_video = get_video_full_path(video_path) if not os.path.isabs(video_path) else video_path
    if not os.path.exists(full_video):
        raise FileNotFoundError(f"视频文件不存在: {full_video}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    info = await probe_media(video_path)
    duration = info["duration"]

    cmd = [
        "ffmpeg", "-y", "-i", full_video,
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1",
        output_path,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # Parse stderr for progress
    while True:
        line = await proc.stderr.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="ignore")
        if "time=" in text and emit_event and duration > 0:
            try:
                time_str = text.split("time=")[1].split()[0]
                h, m, s = map(float, time_str.split(":"))
                current = h * 3600 + m * 60 + s
                pct = min(current / duration * 100, 100)
                await emit_event({"type": "progress", "step": "extract", "progress": pct})
            except Exception:
                pass

    await proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("FFmpeg 音频提取失败")

    if not os.path.exists(output_path):
        raise RuntimeError("音频提取失败 - 输出文件未创建")

    return output_path
