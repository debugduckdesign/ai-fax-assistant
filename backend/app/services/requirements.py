from pathlib import Path

from app.config import BACKEND_DIR, Settings, get_settings

BUNDLED_REQUIREMENTS = BACKEND_DIR / "templates" / "requirements.md"


def requirements_path(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    return settings.requirements_path


def ensure_requirements_file(settings: Settings | None = None) -> Path:
    """Copy bundled template onto a volume path when the target is missing."""
    settings = settings or get_settings()
    path = settings.requirements_path
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    if not BUNDLED_REQUIREMENTS.exists():
        raise FileNotFoundError(
            f"Requirements missing at {path} and no bundle at {BUNDLED_REQUIREMENTS}"
        )
    path.write_text(BUNDLED_REQUIREMENTS.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def load_requirements(settings: Settings | None = None) -> str:
    path = ensure_requirements_file(settings)
    return path.read_text(encoding="utf-8")


def save_requirements(content: str, settings: Settings | None = None) -> str:
    path = requirements_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return content
