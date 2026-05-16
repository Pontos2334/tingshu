import re
from datetime import timedelta


def _format_timestamp(seconds: float, sep: str = ",") -> str:
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{millis:03d}"


def generate_srt(segments: list[dict], variant: str = "original") -> str:
    lines = []
    for i, seg in enumerate(segments, 1):
        lines.append(str(i))
        lines.append(f"{_format_timestamp(seg['start_time'], ',')} --> {_format_timestamp(seg['end_time'], ',')}")
        lines.append(_get_text(seg, variant))
        lines.append("")
    return "\n".join(lines)


def generate_vtt(segments: list[dict], variant: str = "original") -> str:
    lines = ["WEBVTT", ""]
    for seg in segments:
        lines.append(f"{_format_timestamp(seg['start_time'], '.')} --> {_format_timestamp(seg['end_time'], '.')}")
        lines.append(_get_text(seg, variant))
        lines.append("")
    return "\n".join(lines)


def generate_txt(segments: list[dict], variant: str = "original") -> str:
    lines = [_get_text(seg, variant) for seg in segments]
    return "\n".join(lines)


def generate_content(segments: list[dict], fmt: str, variant: str) -> str:
    if fmt == "srt":
        return generate_srt(segments, variant)
    elif fmt == "vtt":
        return generate_vtt(segments, variant)
    elif fmt == "txt":
        return generate_txt(segments, variant)
    raise ValueError(f"不支持的格式: {fmt}")


def _get_text(seg: dict, variant: str) -> str:
    original = seg.get("original_text", seg.get("text", ""))
    translated = seg.get("translated_text", "")
    if variant == "original":
        return original
    elif variant == "translated":
        return translated or original
    elif variant == "bilingual":
        if translated:
            return f"{translated}\n{original}"
        return original
    return original


def parse_srt(content: str) -> list[dict]:
    """Parse SRT content into segments. Tolerant of minor formatting issues."""
    segments = []
    blocks = re.split(r"\n\s*\n", content.strip())
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        try:
            timestamp_line = lines[1]
            start_str, end_str = timestamp_line.split("-->")
            start = _parse_timestamp(start_str.strip())
            end = _parse_timestamp(end_str.strip())
            text = "\n".join(lines[2:]).strip()
            if text:
                segments.append({"start": start, "end": end, "text": text})
        except (ValueError, IndexError):
            continue
    return segments


def _parse_timestamp(ts: str) -> float:
    match = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)", ts)
    if match:
        h, m, s, ms = map(int, match.groups())
        return h * 3600 + m * 60 + s + ms / 1000
    return 0.0
