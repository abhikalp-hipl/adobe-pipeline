import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Ensure .env values are available before Settings is instantiated.
load_dotenv(dotenv_path=Path(".env"), override=False)


def _str_from_env(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip() or default


def _int_from_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    SCHEDULER_INTERVAL_SECONDS: int = _int_from_env("SCHEDULER_INTERVAL_SECONDS", 300)
    MAX_FILES_PER_CYCLE: int = _int_from_env("MAX_FILES_PER_CYCLE", 2)
    PROCESSING_DELAY_SECONDS: int = _int_from_env("PROCESSING_DELAY_SECONDS", 5)
    STORAGE_PROVIDER: str = _str_from_env("STORAGE_PROVIDER", "local").lower()
    MS_CLIENT_ID: str = _str_from_env("MS_CLIENT_ID", "")
    MS_CLIENT_SECRET: str = _str_from_env("MS_CLIENT_SECRET", "")
    MS_TENANT_ID: str = _str_from_env("MS_TENANT_ID", "")
    MS_REDIRECT_URI: str = _str_from_env("MS_REDIRECT_URI", "http://localhost:8000/auth/callback")
    FRONTEND_DASHBOARD_URL: str = _str_from_env("FRONTEND_DASHBOARD_URL", "http://localhost:3000/dashboard")
    MAX_PDF_SIZE_MB: int = _int_from_env("MAX_PDF_SIZE_MB", 100)


settings = Settings()

if settings.STORAGE_PROVIDER != "onedrive":
    raise ValueError(
        "Invalid STORAGE_PROVIDER configuration. This deployment requires STORAGE_PROVIDER=onedrive."
    )
