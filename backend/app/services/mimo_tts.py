import asyncio
import base64
import logging

import aiofiles
import httpx

from app.config import settings

logger = logging.getLogger("tingshu.mimo")


async def _call_mimo_api(api_key: str, payload: dict, base_url: str = None, max_retries: int = 3) -> bytes:
    url = f"{(base_url or settings.mimo_base_url).rstrip('/')}/chat/completions"
    last_error = None
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                resp = await client.post(
                    url,
                    headers={
                        "api-key": api_key,
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                audio_b64 = data["choices"][0]["message"]["audio"]["data"]
                return base64.b64decode(audio_b64)
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                logger.warning(f"MiMo API 调用失败 (尝试 {attempt + 1}/{max_retries})，{wait}s 后重试: {e}")
                await asyncio.sleep(wait)
    raise last_error


async def synthesize_preset(api_key: str, voice: str, text: str, styles: list[str] = None, model: str = None, base_url: str = None) -> bytes:
    messages = []
    if styles:
        style_text = " ".join(f"({s})" for s in styles)
        text = f"{style_text}{text}"
    messages.append({"role": "assistant", "content": text})

    payload = {
        "model": model or settings.mimo_model,
        "messages": messages,
        "audio": {"format": "wav", "voice": voice},
        "stream": False,
    }
    return await _call_mimo_api(api_key, payload, base_url)


async def synthesize_design(api_key: str, description: str, text: str, styles: list[str] = None, base_url: str = None) -> bytes:
    messages = [
        {"role": "user", "content": description},
        {"role": "assistant", "content": text},
    ]

    payload = {
        "model": "mimo-v2.5-tts-voicedesign",
        "messages": messages,
        "audio": {"format": "wav"},
        "stream": False,
    }
    return await _call_mimo_api(api_key, payload, base_url)


async def synthesize_clone(api_key: str, sample_path: str, text: str, styles: list[str] = None, base_url: str = None) -> bytes:
    async with aiofiles.open(sample_path, "rb") as f:
        sample_bytes = await f.read()

    sample_b64 = base64.b64encode(sample_bytes).decode()
    mime = "audio/wav" if sample_path.endswith(".wav") else "audio/mpeg"
    voice_data = f"data:{mime};base64,{sample_b64}"

    messages = [
        {"role": "user", "content": ""},
        {"role": "assistant", "content": text},
    ]

    payload = {
        "model": "mimo-v2.5-tts-voiceclone",
        "messages": messages,
        "audio": {"format": "wav", "voice": voice_data},
        "stream": False,
    }
    return await _call_mimo_api(api_key, payload, base_url)
