from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, Boolean, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class AudioRecord(Base):
    __tablename__ = "audio_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    text_content = Column(Text, nullable=False)
    voice_name = Column(String)
    voice_id = Column(Integer, ForeignKey("custom_voices.id"), nullable=True)
    model = Column(String, default="mimo-v2.5-tts")
    styles = Column(Text)  # JSON array
    file_path = Column(String, nullable=False)
    file_size = Column(Integer)
    duration = Column(Float)
    is_favorite = Column(Boolean, default=False)
    group_id = Column(String)
    chunk_index = Column(Integer, default=0)
    task_id = Column(String, ForeignKey("synthesis_tasks.task_id"), nullable=True, index=True)
    is_merged = Column(Boolean, default=False)
    source_group_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=utcnow)

    playlist_tracks = relationship("PlaylistTrack", back_populates="audio", cascade="all, delete-orphan")


class SynthesisTask(Base):
    __tablename__ = "synthesis_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String, unique=True, nullable=False, index=True)
    title = Column(String, nullable=False)
    full_text = Column(Text, nullable=False)
    chunk_size = Column(Integer, default=500)
    total_chunks = Column(Integer, nullable=False)
    completed_chunks = Column(Integer, default=0)
    failed_chunks = Column(Integer, default=0)
    status = Column(String, default="pending")  # pending/running/completed/failed/partial/canceled
    voice_name = Column(String)
    voice_id = Column(Integer, nullable=True)
    model = Column(String, default="mimo-v2.5-tts")
    styles = Column(Text)  # JSON array
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    chunks = relationship("SynthesisChunk", back_populates="task", cascade="all, delete-orphan")


class SynthesisChunk(Base):
    __tablename__ = "synthesis_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String, ForeignKey("synthesis_tasks.task_id"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    text_content = Column(Text, nullable=False)
    status = Column(String, default="pending")  # pending/running/completed/failed
    retry_count = Column(Integer, default=0)
    audio_record_id = Column(Integer, ForeignKey("audio_records.id"), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    task = relationship("SynthesisTask", back_populates="chunks")


class CustomVoice(Base):
    __tablename__ = "custom_voices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # 'design' or 'clone'
    description = Column(Text)
    sample_path = Column(String)
    preview_path = Column(String)
    model = Column(String, nullable=False)
    created_at = Column(DateTime, default=utcnow)


class Playlist(Base):
    __tablename__ = "playlists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=utcnow)

    tracks = relationship("PlaylistTrack", back_populates="playlist", cascade="all, delete-orphan")


class PlaylistTrack(Base):
    __tablename__ = "playlist_tracks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    playlist_id = Column(Integer, ForeignKey("playlists.id"), nullable=False)
    audio_id = Column(Integer, ForeignKey("audio_records.id"), nullable=False)
    sort_order = Column(Integer, default=0)
    added_at = Column(DateTime, default=utcnow)

    playlist = relationship("Playlist", back_populates="tracks")
    audio = relationship("AudioRecord", back_populates="playlist_tracks")


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=utcnow)


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    system_prompt = Column(Text, nullable=False)
    user_prompt_template = Column(Text, nullable=False)
    style_example = Column(Text, nullable=True)  # 风格参考文章
    model = Column(String, default="deepseek-chat")
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class AIGeneration(Base):
    __tablename__ = "ai_generations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    template_id = Column(Integer, ForeignKey("prompt_templates.id"), nullable=True)
    topic = Column(Text, nullable=False)
    generated_text = Column(Text, nullable=False)
    model = Column(String)
    created_at = Column(DateTime, default=utcnow)


class SubtitleProject(Base):
    __tablename__ = "subtitle_projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    video_path = Column(String, nullable=True)
    audio_path = Column(String, nullable=True)
    video_filename = Column(String, nullable=True)
    video_duration = Column(Float, nullable=True)
    video_size = Column(Integer, nullable=True)

    status = Column(String, default="draft")
    current_step = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)

    asr_engine = Column(String, default="whisper")
    faster_whisper_model = Column(String, default="base")
    whisper_api_model = Column(String, default="whisper-1")
    detected_language = Column(String, nullable=True)

    target_language = Column(String, default="简体中文")
    translator_model = Column(String, default="deepseek-chat")
    context_hint = Column(Text, nullable=True)

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    segments = relationship("SubtitleSegment", back_populates="project", cascade="all, delete-orphan")
    outputs = relationship("SubtitleOutput", back_populates="project", cascade="all, delete-orphan")


class SubtitleSegment(Base):
    __tablename__ = "subtitle_segments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("subtitle_projects.id"), nullable=False, index=True)
    segment_index = Column(Integer, nullable=False)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    original_text = Column(Text, nullable=False)
    translated_text = Column(Text, nullable=True)
    is_edited = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)

    project = relationship("SubtitleProject", back_populates="segments")


class SubtitleOutput(Base):
    __tablename__ = "subtitle_outputs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("subtitle_projects.id"), nullable=False, index=True)
    format = Column(String, nullable=False)
    variant = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    project = relationship("SubtitleProject", back_populates="outputs")
