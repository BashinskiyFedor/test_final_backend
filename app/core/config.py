from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "My App"
    debug: bool = False
    database_url: str = "sqlite+aiosqlite:///./app.db"

    # Keitaro Admin API: базовый URL трекера (без /admin_api/v1) и ключ из настроек трекера.
    keitaro_url: str = "http://localhost"
    keitaro_api_key: str = ""
    # Адреса фронтенда, которым разрешён CORS (через запятую).
    cors_origins: str = "http://localhost:5173"


settings = Settings()
