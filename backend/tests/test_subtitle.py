import sys
from pathlib import Path

import pytest
import pytest_asyncio
import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import Base
from app.db_models import SubtitleProject, SubtitleSegment, SubtitleOutput
from app.services import subtitle_llm_service
from app.services.subtitle_asr_service import build_audio_transcriptions_url
from app.services.subtitle_export_service import generate_srt, generate_vtt, generate_txt, parse_srt
from app.services.subtitle_llm_service import SubtitleLLMError, build_chat_completions_url
from app.services.subtitle_pipeline_service import SegmentCounts, normalize_target_step, plan_pipeline_steps
from app.services.subtitle_translator_service import translate_segments


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


# ── Export service tests ──────────────────────────────

def test_generate_srt_original():
    segments = [
        {"start_time": 0.0, "end_time": 2.5, "original_text": "Hello world", "translated_text": "你好世界"},
        {"start_time": 3.0, "end_time": 5.0, "original_text": "Goodbye", "translated_text": "再见"},
    ]
    result = generate_srt(segments, "original")
    assert "Hello world" in result
    assert "Goodbye" in result
    assert "你好世界" not in result
    assert "00:00:00,000 --> 00:00:02,500" in result


def test_generate_srt_bilingual():
    segments = [
        {"start_time": 0.0, "end_time": 2.5, "original_text": "Hello", "translated_text": "你好"},
    ]
    result = generate_srt(segments, "bilingual")
    assert "你好" in result
    assert "Hello" in result


def test_generate_vtt():
    segments = [
        {"start_time": 0.0, "end_time": 2.5, "original_text": "Test", "translated_text": "测试"},
    ]
    result = generate_vtt(segments, "original")
    assert result.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:02.500" in result


def test_generate_txt():
    segments = [
        {"start_time": 0.0, "end_time": 2.5, "original_text": "Line one", "translated_text": "第一行"},
        {"start_time": 3.0, "end_time": 5.0, "original_text": "Line two", "translated_text": "第二行"},
    ]
    result = generate_txt(segments, "original")
    assert result == "Line one\nLine two"


def test_parse_srt():
    content = """1
00:00:00,000 --> 00:00:02,500
Hello world

2
00:00:03,000 --> 00:00:05,000
Goodbye"""
    segments = parse_srt(content)
    assert len(segments) == 2
    assert segments[0]["text"] == "Hello world"
    assert segments[0]["start"] == 0.0
    assert segments[1]["text"] == "Goodbye"
    assert segments[1]["end"] == 5.0


# ── Database model tests ──────────────────────────────

@pytest.mark.asyncio
async def test_create_subtitle_project(db_session):
    project = SubtitleProject(name="测试项目", asr_engine="whisper", target_language="简体中文")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    assert project.id is not None
    assert project.name == "测试项目"
    assert project.status == "draft"
    assert project.asr_engine == "whisper"


@pytest.mark.asyncio
async def test_subtitle_segments_cascade(db_session):
    project = SubtitleProject(name="级联测试")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    seg1 = SubtitleSegment(project_id=project.id, segment_index=0, start_time=0.0, end_time=2.0, original_text="第一段")
    seg2 = SubtitleSegment(project_id=project.id, segment_index=1, start_time=2.0, end_time=4.0, original_text="第二段", translated_text="Second")
    db_session.add_all([seg1, seg2])
    await db_session.commit()

    from sqlalchemy import select
    result = await db_session.execute(select(SubtitleSegment).where(SubtitleSegment.project_id == project.id))
    segments = result.scalars().all()
    assert len(segments) == 2

    # Test cascade delete
    await db_session.delete(project)
    await db_session.commit()

    result = await db_session.execute(select(SubtitleSegment).where(SubtitleSegment.project_id == project.id))
    remaining = result.scalars().all()
    assert len(remaining) == 0


@pytest.mark.asyncio
async def test_subtitle_output(db_session):
    project = SubtitleProject(name="导出测试")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    output = SubtitleOutput(project_id=project.id, format="srt", variant="bilingual", file_path="20260516/test.srt", file_size=1024)
    db_session.add(output)
    await db_session.commit()

    from sqlalchemy import select
    result = await db_session.execute(select(SubtitleOutput).where(SubtitleOutput.project_id == project.id))
    outputs = result.scalars().all()
    assert len(outputs) == 1
    assert outputs[0].format == "srt"
    assert outputs[0].variant == "bilingual"


# ── Pipeline planning tests ───────────────────────────

def test_normalize_legacy_subtitle_targets():
    assert normalize_target_step("polish") == "translate_polish"
    assert normalize_target_step("polish_no_translate") == "polish_source"
    assert normalize_target_step("translate") == "translate"


def test_pipeline_plan_for_srt_translate_skips_transcribe_and_gpu():
    project = SubtitleProject(name="SRT", asr_engine="whisper")
    steps = plan_pipeline_steps(project, SegmentCounts(total=2), "translate")
    assert steps == ["translate"]


def test_pipeline_plan_adds_missing_video_prerequisites():
    project = SubtitleProject(name="视频", video_path="video.mp4", asr_engine="whisper")
    steps = plan_pipeline_steps(project, SegmentCounts(total=0), "translate_polish")
    assert steps == ["extract", "transcribe", "polish", "translate"]


def test_pipeline_plan_uses_uploaded_audio_without_extract():
    project = SubtitleProject(name="音频", audio_path="audio.wav", asr_engine="whisper_api")
    steps = plan_pipeline_steps(project, SegmentCounts(total=0), "polish_source")
    assert steps == ["transcribe", "polish"]


def test_pipeline_plan_rejects_missing_source():
    project = SubtitleProject(name="空项目")
    with pytest.raises(ValueError, match="请先上传"):
        plan_pipeline_steps(project, SegmentCounts(total=0), "translate")


# ── LLM call and parsing tests ────────────────────────

def test_openai_compatible_urls_do_not_duplicate_v1():
    assert build_chat_completions_url("https://api.deepseek.com/v1") == "https://api.deepseek.com/v1/chat/completions"
    assert build_audio_transcriptions_url("https://api.openai.com/v1") == "https://api.openai.com/v1/audio/transcriptions"


def _mock_async_client(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        return original_client(transport=transport, timeout=kwargs.get("timeout"))

    monkeypatch.setattr(subtitle_llm_service.httpx, "AsyncClient", factory)


@pytest.mark.asyncio
async def test_translate_segments_parses_json_array(monkeypatch):
    seen_urls = []

    def handler(request):
        seen_urls.append(str(request.url))
        return httpx.Response(200, json={"choices": [{"message": {"content": '["你好", "再见"]'}}]})

    _mock_async_client(monkeypatch, handler)
    result = await translate_segments(
        [
            {"start": 0.0, "end": 1.0, "text": "Hello"},
            {"start": 1.0, "end": 2.0, "text": "Bye"},
        ],
        "sk-test",
        "https://api.deepseek.com/v1",
    )

    assert [item["text"] for item in result] == ["你好", "再见"]
    assert seen_urls == ["https://api.deepseek.com/v1/chat/completions"]


@pytest.mark.asyncio
async def test_translate_segments_retries_when_count_mismatches(monkeypatch):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        content = '["只有一条"]' if calls == 1 else '["第一条", "第二条"]'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    _mock_async_client(monkeypatch, handler)
    result = await translate_segments(
        [
            {"start": 0.0, "end": 1.0, "text": "one"},
            {"start": 1.0, "end": 2.0, "text": "two"},
        ],
        "sk-test",
        "https://api.deepseek.com/v1",
    )

    assert calls == 2
    assert [item["text"] for item in result] == ["第一条", "第二条"]


@pytest.mark.asyncio
async def test_translate_segments_raises_http_error_with_response_detail(monkeypatch):
    def handler(request):
        return httpx.Response(429, text="rate limit exceeded")

    _mock_async_client(monkeypatch, handler)

    with pytest.raises(SubtitleLLMError) as exc_info:
        await translate_segments(
            [{"start": 0.0, "end": 1.0, "text": "hello"}],
            "sk-test",
            "https://api.deepseek.com/v1",
        )

    assert exc_info.value.code == "llm_http_error"
    assert "rate limit" in exc_info.value.detail
