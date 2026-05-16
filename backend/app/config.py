from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mimo_api_key: str = ""
    mimo_base_url: str = "https://api.xiaomimimo.com/v1"
    mimo_model: str = "mimo-v2.5-tts"
    admin_token: str = ""
    audio_storage_path: str = "./data/audio"
    sample_storage_path: str = "./data/samples"
    database_url: str = "sqlite+aiosqlite:///./data/tingshu.db"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # 字幕翻译
    video_storage_path: str = "./data/subtitle_videos"
    subtitle_storage_path: str = "./data/subtitles"
    max_video_size_mb: int = 2048
    whisper_api_key: str = ""
    whisper_api_base_url: str = "https://api.openai.com/v1"
    xunfei_appid: str = ""
    xunfei_api_key: str = ""
    xunfei_api_secret: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
