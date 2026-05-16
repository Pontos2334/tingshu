import logging
from typing import Callable

from app.services.subtitle_llm_service import run_segment_llm_batches

logger = logging.getLogger("tingshu.subtitle.polish")


def _language_name(source_language: str) -> str:
    lang_map = {
        "zh": "Chinese",
        "en": "English",
        "ja": "Japanese",
        "ko": "Korean",
        "fr": "French",
        "de": "German",
        "es": "Spanish",
    }
    return lang_map.get(source_language, source_language)


def _context_block(context_texts: list[str]) -> str:
    if not context_texts:
        return ""
    return "\nPrevious polished context, for continuity only:\n" + "\n".join(f"- {t}" for t in context_texts)


async def polish_segments(
    segments: list[dict],
    api_key: str,
    base_url: str,
    model: str = "deepseek-chat",
    source_language: str = "auto",
    context_hint: str | None = None,
    emit_event: Callable | None = None,
    project_id: int | None = None,
) -> list[dict]:
    """Polish source-language subtitle segments without translating them."""
    hint = context_hint.strip() if context_hint and context_hint.strip() else ""
    lang_instruction = ""
    if source_language and source_language != "auto":
        lang_instruction = f"The source language is {_language_name(source_language)}. "

    system_content = (
        "You are a professional subtitle editor. Fix typos, ASR recognition errors, punctuation, "
        "and minor subtitle wording issues. Never translate or change the meaning. Return only valid JSON."
    )
    if hint:
        system_content += f"\n\nContext about this video: {hint}"

    def make_prompt(batch_texts: list[str], context_texts: list[str], retry: bool) -> str:
        retry_instruction = ""
        if retry:
            retry_instruction = "\nYour previous answer could not be parsed. Return a JSON string array with exactly the same number of items."
        texts = "\n".join(f"{i + 1}. {text}" for i, text in enumerate(batch_texts))
        hint_block = f"\nVideo context hint: {hint}\n" if hint else ""
        return f"""Polish the following numbered subtitle texts. {lang_instruction}{retry_instruction}
{hint_block}{_context_block(context_texts)}

Texts to polish:
{texts}

Rules:
1. Fix typos, ASR errors, incorrect characters, and punctuation.
2. Keep the original language.
3. Do not translate.
4. Do not merge, split, add, or remove items.
5. Preserve meaning and tone.
6. Return ONLY a JSON string array, for example: ["润色后1", "润色后2"].
"""

    return await run_segment_llm_batches(
        segments=segments,
        api_key=api_key,
        base_url=base_url,
        model=model,
        operation="润色",
        system_content=system_content,
        make_prompt=make_prompt,
        temperature=0.2,
        progress_step="polish",
        progress_message="已润色 {done}/{total} 段",
        logger=logger,
        project_id=project_id,
        emit_event=emit_event,
    )
