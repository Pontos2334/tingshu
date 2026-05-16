import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import ssl
import time
from datetime import datetime
from time import mktime
from typing import Callable
from urllib.parse import urlencode
from wsgiref.handlers import format_date_time

import httpx

from app.config import settings

logger = logging.getLogger("tingshu.subtitle.asr")

# Module-level model cache for Faster-Whisper
_loaded_models: dict[str, object] = {}


async def transcribe_whisper(
    audio_path: str,
    model: str = "base",
    language: str | None = None,
    emit_event: Callable | None = None,
) -> dict:
    """Transcribe using local Faster-Whisper model."""
    if emit_event:
        await emit_event({"type": "progress", "step": "transcribe", "message": f"正在加载 Whisper {model} 模型...", "progress": 0})

    def _run():
        nonlocal model
        if model not in _loaded_models:
            from faster_whisper import WhisperModel
            try:
                _loaded_models[model] = WhisperModel(model, device="auto", compute_type="float16")
            except Exception:
                _loaded_models[model] = WhisperModel(model, device="cpu", compute_type="int8")
        return _loaded_models[model]

    whisper_model = await asyncio.to_thread(_run)

    if emit_event:
        await emit_event({"type": "progress", "step": "transcribe", "message": "模型加载完成，开始识别...", "progress": 10})

    def _transcribe():
        kwargs = dict(beam_size=5, vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500))
        if language:
            kwargs["language"] = language
        segments_gen, info = whisper_model.transcribe(audio_path, **kwargs)
        all_segments = list(segments_gen)
        return all_segments, info

    segments_list, info = await asyncio.to_thread(_transcribe)

    converted = []
    all_text = ""
    for seg in segments_list:
        text = seg.text.strip()
        all_text += text
        converted.append({"start": seg.start, "end": seg.end, "text": text})

    if emit_event:
        await emit_event({"type": "progress", "step": "transcribe", "message": f"识别完成，共 {len(converted)} 段", "progress": 100})

    return {"text": all_text, "language": info.language if info else "unknown", "segments": converted}


async def transcribe_whisper_api(
    audio_path: str,
    api_key: str | None = None,
    base_url: str | None = None,
    language: str | None = None,
    emit_event: Callable | None = None,
    model: str = "whisper-1",
) -> dict:
    """Transcribe using OpenAI-compatible Whisper API."""
    key = api_key or settings.whisper_api_key
    url = base_url or settings.whisper_api_base_url
    if not key:
        raise ValueError("未配置 Whisper API Key")

    if emit_event:
        await emit_event({"type": "progress", "step": "transcribe", "message": "正在上传音频到 Whisper API...", "progress": 0})

    async with httpx.AsyncClient(base_url=url, timeout=300) as client:
        with open(audio_path, "rb") as f:
            files = {"file": (os.path.basename(audio_path), f, "audio/wav")}
            data = {"model": model, "response_format": "verbose_json"}
            if language:
                data["language"] = language
            resp = await client.post("/v1/audio/transcriptions", headers={"Authorization": f"Bearer {key}"}, files=files, data=data)
            resp.raise_for_status()

    result = resp.json()
    converted = []
    for seg in result.get("segments", []):
        converted.append({"start": seg["start"], "end": seg["end"], "text": seg["text"]})

    if emit_event:
        await emit_event({"type": "progress", "step": "transcribe", "message": "API 识别完成", "progress": 100})

    return {"text": result.get("text", ""), "language": result.get("language", "unknown"), "segments": converted}


async def transcribe_xunfei(
    audio_path: str,
    appid: str | None = None,
    api_key: str | None = None,
    api_secret: str | None = None,
    language: str = "zh_cn",
    emit_event: Callable | None = None,
) -> dict:
    """Transcribe using Xunfei IAT (runs in thread due to sync websocket)."""
    _appid = appid or settings.xunfei_appid
    _api_key = api_key or settings.xunfei_api_key
    _api_secret = api_secret or settings.xunfei_api_secret
    if not all([_appid, _api_key, _api_secret]):
        raise ValueError("未配置讯飞 APPID/APIKey/APISecret")

    if emit_event:
        await emit_event({"type": "progress", "step": "transcribe", "message": "正在使用讯飞语音识别...", "progress": 0})

    def _run():
        import websocket as ws_lib

        result_text = ""
        result_segments = []
        is_finished = False
        error_msg = None

        accent = "mandarin" if language == "zh_cn" else ""

        def _create_url():
            url_base = "wss://iat.cn-huabei-1.xf-yun.com/v1"
            now = datetime.now()
            date = format_date_time(mktime(now.timetuple()))
            sig_origin = f"host: iat.cn-huabei-1.xf-yun.com\ndate: {date}\nGET /v1 HTTP/1.1"
            sig_sha = hmac.new(_api_secret.encode(), sig_origin.encode(), hashlib.sha256).digest()
            sig_b64 = base64.b64encode(sig_sha).decode()
            auth_origin = f'api_key="{_api_key}", algorithm="hmac-sha256", headers="host date request-line", signature="{sig_b64}"'
            auth_b64 = base64.b64encode(auth_origin.encode()).decode()
            return url_base + "?" + urlencode({"authorization": auth_b64, "date": date, "host": "iat.cn-huabei-1.xf-yun.com"})

        def _on_message(ws, message):
            nonlocal result_text, is_finished, error_msg
            msg = json.loads(message)
            code = msg["header"]["code"]
            status = msg["header"]["status"]
            if code != 0:
                error_msg = f"讯飞错误: {code}"
                ws.close()
                return
            payload = msg.get("payload")
            if payload:
                text_data = json.loads(base64.b64decode(payload["result"]["text"]).decode())
                seg_text = ""
                for item in text_data.get("ws", []):
                    for cw in item.get("cw", []):
                        seg_text += cw.get("w", "")
                if seg_text:
                    result_text += seg_text
                    pg = text_data.get("pg", {})
                    if pg:
                        result_segments.append({"text": seg_text, "bg": pg.get("bg", 0), "ed": pg.get("ed", 0)})
            if status == 2:
                is_finished = True
                ws.close()

        def _on_error(ws, error):
            nonlocal error_msg, is_finished
            error_msg = str(error)
            is_finished = True

        def _on_close(ws, *args):
            nonlocal is_finished
            is_finished = True

        def _on_open(ws):
            def _send():
                frame_size = 1280
                status = 0  # FIRST_FRAME
                with open(audio_path, "rb") as fp:
                    fp.seek(44)  # Skip WAV header (44 bytes for PCM s16le)
                    while not is_finished:
                        buf = fp.read(frame_size)
                        audio_b64 = base64.b64encode(buf).decode() if buf else ""
                        if not audio_b64:
                            status = 2  # LAST_FRAME
                        if status == 0:
                            d = {"header": {"status": 0, "app_id": _appid}, "parameter": {"iat": {"domain": "iat", "language": language, "accent": accent, "vad_eos": 3000, "result": {"encoding": "utf8", "compress": "raw", "format": "json"}}}, "payload": {"audio": {"audio": audio_b64, "sample_rate": 16000, "encoding": "raw", "status": 0}}}
                            ws.send(json.dumps(d))
                            status = 1
                        elif status == 1:
                            d = {"header": {"status": 1, "app_id": _appid}, "payload": {"audio": {"audio": audio_b64, "sample_rate": 16000, "encoding": "raw", "status": 1}}}
                            ws.send(json.dumps(d))
                        elif status == 2:
                            d = {"header": {"status": 2, "app_id": _appid}, "payload": {"audio": {"audio": "", "sample_rate": 16000, "encoding": "raw", "status": 2}}}
                            ws.send(json.dumps(d))
                            break
                        time.sleep(0.04)
            import threading
            threading.Thread(target=_send, daemon=True).start()

        ws = ws_lib.WebSocketApp(_create_url(), on_message=_on_message, on_error=_on_error, on_close=_on_close)
        ws.on_open = _on_open
        ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

        if error_msg:
            raise RuntimeError(error_msg)

        # Convert segments
        converted = []
        current_time = 0.0
        for seg in result_segments:
            text = seg["text"].strip()
            if text:
                bg = seg.get("bg")
                ed = seg.get("ed")
                if bg is not None and ed is not None:
                    start = bg / 100.0
                    end = ed / 100.0
                else:
                    start = current_time
                    end = start + len(text) * 0.3
                converted.append({"start": start, "end": end, "text": text})
                current_time = end

        return {"text": result_text, "language": language, "segments": converted}

    return await asyncio.to_thread(_run)
