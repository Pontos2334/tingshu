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

    class Config:
        env_file = ".env"


settings = Settings()
