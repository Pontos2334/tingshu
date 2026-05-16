import asyncio
import logging
import re
from typing import Callable

import httpx

logger = logging.getLogger("tingshu.subtitle.translator")

MAX_CHARS_PER_BATCH = 3000
CONTEXT_WINDOW = 3


def _parse_numbered_response(response: str, expected_count: int) -> list[str]:
    lines = response.strip().split("\n")
    results = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^\d+\.\s*(.+)$", line)
        if match:
            results.append(match.group(1).strip())
        elif results:
            results[-1] += " " + line
        elif len(results) < expected_count:
            results.append(line)
    while len(results) < expected_count:
        results.append("")
    return results[:expected_count]


async def translate_segments(
    segments: list[dict],
    api_key: str,
    base_url: str,
    model: str = "deepseek-chat",
    target_language: str = "简体中文",
    context_hint: str | None = None,
    emit_event: Callable | None = None,
) -> list[dict]:
    """Translate subtitle segments, preserving timestamps."""
    if not api_key:
        raise ValueError("未配置翻译 API Key")
    if not segments:
        return []

    total = len(segments)
    translated = []
    i = 0

    async with httpx.AsyncClient(base_url=base_url, timeout=60) as client:
        while i < total:
            # Build batch by character count
            batch_end = i
            batch_chars = 0
            while batch_end < total and batch_chars < MAX_CHARS_PER_BATCH:
                seg_text = segments[batch_end]["text"]
                if batch_chars + len(seg_text) > MAX_CHARS_PER_BATCH and batch_end > i:
                    break
                batch_chars += len(seg_text)
                batch_end += 1

            batch = segments[i:batch_end]
            batch_texts = [s["text"] for s in batch]

            # Context from previous segments
            context_count = min(CONTEXT_WINDOW, len(translated))
            context_texts = [s["text"] for s in translated[-context_count:]]

            context_str = ""
            if context_texts:
                context_str = "\nPrevious context (for reference only, do not translate):\n"
                context_str += "\n".join(f"- {t}" for t in context_texts)

            hint_str = ""
            if context_hint and context_hint.strip():
                hint_str = f"\nVideo context hint: {context_hint.strip()}\n"

            texts_str = "\n".join(f"{j + 1}. {t}" for j, t in enumerate(batch_texts))

            prompt = f"""Translate the following numbered texts to {target_language}.
{hint_str}{context_str}

Texts to translate:
{texts_str}

Instructions:
1. Translate each numbered text independently
2. Preserve the original tone and meaning
3. Keep the translation concise (suitable for subtitles)
4. Return ONLY the translated texts in the same numbered format, nothing else

Translated texts:"""

            system_content = f"You are a professional subtitle translator. Translate text to {target_language} accurately, concisely, and naturally for subtitles."
            if context_hint and context_hint.strip():
                system_content += f"\n\nContext about this video: {context_hint.strip()}"

            resp = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_content},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 4000,
                },
            )
            resp.raise_for_status()
            response_text = resp.json()["choices"][0]["message"]["content"].strip()
            translated_texts = _parse_numbered_response(response_text, len(batch_texts))

            for j, (original, trans) in enumerate(zip(batch, translated_texts)):
                translated.append({
                    "start": original["start"],
                    "end": original["end"],
                    "text": trans,
                    "original_text": original["text"],
                })

            if emit_event:
                pct = min(batch_end / total * 100, 100)
                await emit_event({"type": "progress", "step": "translate", "message": f"已翻译 {batch_end}/{total} 段", "progress": pct})

            i = batch_end

    return translated
