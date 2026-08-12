from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    elevenlabs_api_key: str = ""
    elevenlabs_agent_id: str = ""
    elevenlabs_agent_phone_number_id: str = ""
    elevenlabs_webhook_secret: str = ""
    # Local-only escape hatch; never enable in shared/prod environments.
    allow_insecure_webhooks: bool = False
    api_key: str = ""
    data_dir: Path = ROOT_DIR / "data"
    database_path: Path = ROOT_DIR / "data" / "app.db"
    redis_url: str = "redis://localhost:6379/0"
    session_secret: str = "dev-session-secret-change-me"
    session_ttl_seconds: int = 60 * 60 * 24 * 7
    session_cookie_name: str = "session_id"
    # Set true behind HTTPS so browsers won't send the cookie over plain HTTP.
    session_cookie_secure: bool = False
    admin_username: str = "admin"
    admin_password: str = "admin"
    webhook_base_url: str = "http://localhost:8000"
    confidence_threshold: float = 0.7
    max_upload_bytes: int = 20 * 1024 * 1024
    max_requirements_chars: int = 200_000
    min_password_length: int = 8
    login_rate_limit: int = 20
    login_rate_window_seconds: int = 60
    requirements_path: Path = BACKEND_DIR / "templates" / "requirements.md"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]

    @property
    def cases_dir(self) -> Path:
        return self.data_dir / "cases"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if not settings.data_dir.is_absolute():
        settings.data_dir = (ROOT_DIR / settings.data_dir).resolve()
    else:
        settings.data_dir = settings.data_dir.resolve()
    if not settings.database_path.is_absolute():
        settings.database_path = (ROOT_DIR / settings.database_path).resolve()
    else:
        settings.database_path = settings.database_path.resolve()
    if not settings.requirements_path.is_absolute():
        settings.requirements_path = (
            BACKEND_DIR / settings.requirements_path
        ).resolve()
    else:
        settings.requirements_path = settings.requirements_path.resolve()
    settings.cases_dir.mkdir(parents=True, exist_ok=True)
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    return settings
