import json
import logging
import re
import time
from typing import Callable
from urllib.parse import urlparse

import httpx

MAX_CHARS_PER_BATCH = 3000
CONTEXT_WINDOW = 3


class SubtitleLLMError(RuntimeError):
    def __init__(self, message: str, code: str = "llm_error", detail: str | None = None):
        super().__init__(message)
        self.code = code
        self.detail = detail or message


def build_chat_completions_url(base_url: str) -> str:
    normalized = (base_url or "").rstrip("/")
    if not normalized:
        raise SubtitleLLMError("未配置 AI 接口地址", code="llm_base_url_missing")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def safe_url_label(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def split_batches(segments: list[dict]) -> list[tuple[int, int, list[dict]]]:
    batches = []
    i = 0
    total = len(segments)
    while i < total:
        batch_end = i
        batch_chars = 0
        while batch_end < total and batch_chars < MAX_CHARS_PER_BATCH:
            seg_text = segments[batch_end]["text"] or ""
            if batch_chars + len(seg_text) > MAX_CHARS_PER_BATCH and batch_end > i:
                break
            batch_chars += len(seg_text)
            batch_end += 1
        if batch_end == i:
            batch_end += 1
        batches.append((i, batch_end, segments[i:batch_end]))
        i = batch_end
    return batches


def parse_numbered_response(response: str, expected_count: int) -> list[str]:
    lines = response.strip().split("\n")
    results = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^\s*(\d+)[.)、]\s*(.+)$", line)
        if match:
            results.append(match.group(2).strip())
        elif results:
            results[-1] += " " + line
        else:
            results.append(line)
    if len(results) != expected_count:
        raise SubtitleLLMError(
            f"AI 返回条数不匹配: 期望 {expected_count} 条，实际 {len(results)} 条",
            code="llm_response_count_mismatch",
            detail=response[:1200],
        )
    if any(not item.strip() for item in results):
        raise SubtitleLLMError("AI 返回了空字幕内容", code="llm_response_empty_item", detail=response[:1200])
    return results


def parse_json_array_response(response: str, expected_count: int) -> list[str]:
    text = response.strip()
    fence_match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.S)
    if fence_match:
        text = fence_match.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SubtitleLLMError("AI 返回不是合法 JSON", code="llm_response_invalid_json", detail=response[:1200]) from exc

    if isinstance(data, dict):
        for key in ("items", "results", "translations", "polished", "texts"):
            if isinstance(data.get(key), list):
                data = data[key]
                break

    if not isinstance(data, list):
        raise SubtitleLLMError("AI 返回 JSON 不是数组", code="llm_response_not_array", detail=response[:1200])

    results = []
    for item in data:
        if isinstance(item, str):
            results.append(item.strip())
        elif isinstance(item, dict):
            value = item.get("text") or item.get("translation") or item.get("result") or item.get("content")
            results.append(str(value or "").strip())
        else:
            results.append(str(item).strip())

    if len(results) != expected_count:
        raise SubtitleLLMError(
            f"AI 返回条数不匹配: 期望 {expected_count} 条，实际 {len(results)} 条",
            code="llm_response_count_mismatch",
            detail=response[:1200],
        )
    if any(not item for item in results):
        raise SubtitleLLMError("AI 返回了空字幕内容", code="llm_response_empty_item", detail=response[:1200])
    return results


def parse_llm_list_response(response: str, expected_count: int) -> list[str]:
    try:
        return parse_json_array_response(response, expected_count)
    except SubtitleLLMError as json_error:
        try:
            return parse_numbered_response(response, expected_count)
        except SubtitleLLMError as numbered_error:
            numbered_error.detail = json_error.detail or numbered_error.detail
            raise numbered_error


def response_summary(text: str, limit: int = 1200) -> str:
    normalized = " ".join((text or "").split())
    return normalized[:limit]


async def post_chat_completion(
    *,
    api_key: str,
    base_url: str,
    model: str,
    system_content: str,
    user_content: str,
    temperature: float,
    logger: logging.Logger,
    operation: str,
    project_id: int | None,
    batch_index: int,
    segment_start: int,
    segment_end: int,
    timeout: int = 120,
) -> str:
    if not api_key:
        raise SubtitleLLMError(f"未配置{operation} API Key", code="llm_api_key_missing")

    url = build_chat_completions_url(base_url)
    safe_url = safe_url_label(url)
    started = time.monotonic()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "max_tokens": 4000,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        detail = response_summary(exc.response.text)
        logger.warning(
            "字幕%s HTTP 失败: project_id=%s batch=%s segments=%s-%s model=%s url=%s status=%s detail=%s",
            operation,
            project_id,
            batch_index,
            segment_start + 1,
            segment_end,
            model,
            safe_url,
            exc.response.status_code,
            detail,
        )
        raise SubtitleLLMError(
            f"{operation}接口请求失败: HTTP {exc.response.status_code}",
            code="llm_http_error",
            detail=detail,
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning(
            "字幕%s连接失败: project_id=%s batch=%s segments=%s-%s model=%s url=%s error=%s",
            operation,
            project_id,
            batch_index,
            segment_start + 1,
            segment_end,
            model,
            safe_url,
            exc,
        )
        raise SubtitleLLMError(f"{operation}接口连接失败: {exc}", code="llm_network_error", detail=str(exc)) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise SubtitleLLMError(f"{operation}接口返回格式异常", code="llm_invalid_payload", detail=str(exc)) from exc

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise SubtitleLLMError(f"{operation}接口返回缺少内容", code="llm_missing_content", detail=json.dumps(data, ensure_ascii=False)[:1200]) from exc

    logger.info(
        "字幕%s批次完成: project_id=%s batch=%s segments=%s-%s model=%s url=%s elapsed=%.2fs chars=%s",
        operation,
        project_id,
        batch_index,
        segment_start + 1,
        segment_end,
        model,
        safe_url,
        time.monotonic() - started,
        len(content or ""),
    )
    return (content or "").strip()


async def run_segment_llm_batches(
    *,
    segments: list[dict],
    api_key: str,
    base_url: str,
    model: str,
    operation: str,
    system_content: str,
    make_prompt: Callable[[list[str], list[str], bool], str],
    temperature: float,
    progress_step: str,
    progress_message: str,
    logger: logging.Logger,
    project_id: int | None = None,
    emit_event: Callable | None = None,
) -> list[dict]:
    if not segments:
        return []

    total = len(segments)
    results: list[dict] = []
    batches = split_batches(segments)

    for batch_index, (batch_start, batch_end, batch) in enumerate(batches, 1):
        batch_texts = [s["text"] for s in batch]
        context_texts = [s["text"] for s in results[-CONTEXT_WINDOW:]]
        last_parse_error: SubtitleLLMError | None = None
        parsed_texts: list[str] | None = None

        for attempt in range(2):
            prompt = make_prompt(batch_texts, context_texts, attempt > 0)
            response_text = await post_chat_completion(
                api_key=api_key,
                base_url=base_url,
                model=model,
                system_content=system_content,
                user_content=prompt,
                temperature=temperature,
                logger=logger,
                operation=operation,
                project_id=project_id,
                batch_index=batch_index,
                segment_start=batch_start,
                segment_end=batch_end,
            )
            try:
                parsed_texts = parse_llm_list_response(response_text, len(batch_texts))
                break
            except SubtitleLLMError as exc:
                last_parse_error = exc
                logger.warning(
                    "字幕%s解析失败: project_id=%s batch=%s segments=%s-%s attempt=%s code=%s detail=%s",
                    operation,
                    project_id,
                    batch_index,
                    batch_start + 1,
                    batch_end,
                    attempt + 1,
                    exc.code,
                    response_summary(exc.detail),
                )

        if parsed_texts is None:
            raise last_parse_error or SubtitleLLMError(f"{operation}结果解析失败", code="llm_response_parse_failed")

        for original, text in zip(batch, parsed_texts):
            results.append({
                "start": original["start"],
                "end": original["end"],
                "text": text,
                "original_text": original["text"],
            })

        if emit_event:
            pct = min(batch_end / total * 100, 100)
            await emit_event({
                "type": "progress",
                "step": progress_step,
                "message": progress_message.format(done=batch_end, total=total),
                "progress": pct,
            })

    return results
