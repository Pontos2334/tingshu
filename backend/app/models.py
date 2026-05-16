import json

from datetime import datetime
from pydantic import BaseModel, field_validator
from typing import Optional


# TTS 请求模型
class SynthesizeRequest(BaseModel):
    text: str
    voice: Optional[str] = "mimo_default"
    voice_id: Optional[int] = None
    styles: list[str] = []
    model: str = "mimo-v2.5-tts"


class SynthesizeLongRequest(BaseModel):
    text: str
    voice: Optional[str] = "mimo_default"
    voice_id: Optional[int] = None
    styles: list[str] = []
    chunk_size: int = 500
    model: str = "mimo-v2.5-tts"


# 音色模型
class VoiceDesignRequest(BaseModel):
    name: str
    description: str
    sample_text: str = "你好，欢迎来到我的听书世界。"


class VoiceOut(BaseModel):
    id: int
    name: str
    type: str
    description: Optional[str] = None
    model: str

    class Config:
        from_attributes = True


# 音频记录模型
class AudioRecordOut(BaseModel):
    id: int
    title: str
    text_content: str
    voice_name: Optional[str] = None
    model: str
    styles: list[str] = []
    file_size: Optional[int] = None
    duration: Optional[float] = None
    is_favorite: bool = False
    group_id: Optional[str] = None
    chunk_index: int = 0
    is_merged: bool = False
    source_group_id: Optional[str] = None
    created_at: Optional[datetime] = None

    @field_validator("styles", mode="before")
    @classmethod
    def parse_styles(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v) if v else []
            except (json.JSONDecodeError, TypeError):
                return []
        return v or []

    class Config:
        from_attributes = True


class AudioGroupSummaryOut(BaseModel):
    group_id: str
    title: str
    voice_name: Optional[str] = None
    clip_count: int
    total_duration: float = 0
    created_at: Optional[datetime] = None
    has_favorite: bool = False
    has_merged: bool = False
    source_type: str


class AudioGroupDetailOut(AudioGroupSummaryOut):
    records: list[AudioRecordOut] = []
    merged_record: Optional[AudioRecordOut] = None


# 播放列表模型
class PlaylistCreate(BaseModel):
    name: str
    description: Optional[str] = None


class PlaylistOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class PlaylistTrackAdd(BaseModel):
    audio_id: int


class PlaylistTrackOut(BaseModel):
    track_id: int
    sort_order: int
    audio: AudioRecordOut


# 合成任务模型
class SynthesisTaskOut(BaseModel):
    task_id: str
    title: str
    total_chunks: int
    completed_chunks: int
    failed_chunks: int
    status: str
    voice_name: Optional[str] = None
    voice_id: Optional[int] = None
    model: str
    styles: list[str] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("styles", mode="before")
    @classmethod
    def parse_styles(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v) if v else []
            except (json.JSONDecodeError, TypeError):
                return []
        return v or []

    class Config:
        from_attributes = True


class SynthesisChunkOut(BaseModel):
    chunk_index: int
    text_preview: str
    status: str
    retry_count: int
    audio_record_id: Optional[int] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class SynthesisTaskDetail(SynthesisTaskOut):
    chunks: list[SynthesisChunkOut] = []


# AI 生成模型
class PromptTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    system_prompt: str
    user_prompt_template: str
    style_example: Optional[str] = None
    model: str = "deepseek-chat"


class PromptTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    user_prompt_template: Optional[str] = None
    style_example: Optional[str] = None
    model: Optional[str] = None


class PromptTemplateOut(BaseModel):
    id: int
    slug: str
    name: str
    description: Optional[str] = None
    system_prompt: str
    user_prompt_template: str
    style_example: Optional[str] = None
    model: str
    is_default: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AIGenerateRequest(BaseModel):
    topic: str
    template_id: Optional[int] = None
    system_prompt: Optional[str] = None
    user_prompt: Optional[str] = None
    model: str = "deepseek-chat"
    max_tokens: int = 4000
    thinking_enabled: bool = False
    reasoning_effort: str = "high"  # high / max


class AIGenerationOut(BaseModel):
    id: int
    template_id: Optional[int] = None
    topic: str
    generated_text: str
    model: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── 字幕翻译模型 ──────────────────────────────────────────

class SubtitleProjectCreate(BaseModel):
    name: str
    asr_engine: str = "whisper"
    faster_whisper_model: str = "base"
    whisper_api_model: str = "whisper-1"
    source_language: str = "auto"
    target_language: str = "简体中文"
    translator_model: str = "deepseek-chat"
    context_hint: Optional[str] = None


class SubtitleProjectUpdate(BaseModel):
    name: Optional[str] = None
    asr_engine: Optional[str] = None
    faster_whisper_model: Optional[str] = None
    whisper_api_model: Optional[str] = None
    source_language: Optional[str] = None
    target_language: Optional[str] = None
    translator_model: Optional[str] = None
    context_hint: Optional[str] = None


class SubtitleSegmentOut(BaseModel):
    id: int
    segment_index: int
    start_time: float
    end_time: float
    original_text: str
    translated_text: Optional[str] = None
    polished_text: Optional[str] = None
    is_edited: bool = False
    original_edited: bool = False
    polished_edited: bool = False
    translated_edited: bool = False

    class Config:
        from_attributes = True


class SubtitleSegmentUpdate(BaseModel):
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    original_text: Optional[str] = None
    translated_text: Optional[str] = None
    polished_text: Optional[str] = None


class SubtitleOutputOut(BaseModel):
    id: int
    format: str
    variant: str
    file_size: Optional[int] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SubtitleProjectOut(BaseModel):
    id: int
    name: str
    video_filename: Optional[str] = None
    video_duration: Optional[float] = None
    video_size: Optional[int] = None
    status: str
    current_step: Optional[str] = None
    asr_engine: str
    source_language: str = "auto"
    target_language: str
    segment_count: int = 0
    translated_count: int = 0
    polished_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SubtitleProjectDetail(SubtitleProjectOut):
    video_path: Optional[str] = None
    audio_path: Optional[str] = None
    error_message: Optional[str] = None
    error_step: Optional[str] = None
    error_code: Optional[str] = None
    error_detail: Optional[str] = None
    faster_whisper_model: str = "base"
    whisper_api_model: str = "whisper-1"
    detected_language: Optional[str] = None
    translator_model: str = "deepseek-chat"
    context_hint: Optional[str] = None
    segments: list[SubtitleSegmentOut] = []
    outputs: list[SubtitleOutputOut] = []


class SubtitleProcessRequest(BaseModel):
    target_step: str  # "extract" | "transcribe" | "translate" | "polish"
    force: bool = False


class SubtitleExportRequest(BaseModel):
    format: str = "srt"  # "srt" | "vtt" | "txt"
    variant: str = "bilingual"  # "original" | "translated" | "bilingual" | "polished"
