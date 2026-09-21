from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Action Memo Demo API"
    app_env: str = "development"
    openai_api_key: str = ""
    openai_transcription_model: str = "gpt-transcribe"
    openai_analysis_model: str = "gpt-4o-mini"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
