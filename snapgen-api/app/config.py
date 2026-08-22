from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = os.getenv("SNAPGEN_APP_NAME", "snapgen.ai API")
    version: str = os.getenv("SNAPGEN_VERSION", "0.1.0")
    environment: str = os.getenv("SNAPGEN_ENVIRONMENT", "development")
    api_key: str | None = os.getenv("SNAPGEN_API_KEY")
    webhook_secret: str = os.getenv("SNAPGEN_WEBHOOK_SECRET", "dev-webhook-secret")
    public_base_url: str = os.getenv("SNAPGEN_PUBLIC_BASE_URL", "http://localhost:8000")
    provider: str = os.getenv("SNAPGEN_PROVIDER", "mock")
    provider_base_url: str | None = os.getenv("SNAPGEN_PROVIDER_BASE_URL")
    provider_api_key: str | None = os.getenv("SNAPGEN_PROVIDER_API_KEY")
    provider_timeout_seconds: float = float(os.getenv("SNAPGEN_PROVIDER_TIMEOUT", "120"))
    storage_dir: Path = Path(os.getenv("SNAPGEN_STORAGE_DIR", "./data/assets"))


settings = Settings()
