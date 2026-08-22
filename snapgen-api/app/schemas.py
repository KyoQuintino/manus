from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GenerationMode(str, Enum):
    TEXT_TO_IMAGE = "TEXT_TO_IMAGE"
    TEXT_TO_VIDEO = "TEXT_TO_VIDEO"
    IMAGE_TO_VIDEO = "IMAGE_TO_VIDEO"


class TaskStatus(str, Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class GenerationRequest(BaseModel):
    """Public request accepted by all media generation endpoints."""

    model_config = ConfigDict(extra="forbid")

    mode: GenerationMode
    prompt: str = Field(min_length=1, max_length=4_000)
    image_url: AnyHttpUrl | None = None
    model: str | None = Field(default=None, min_length=1, max_length=100)
    width: int = Field(default=1024, ge=256, le=4096)
    height: int = Field(default=1024, ge=256, le=4096)
    duration_seconds: int | None = Field(default=None, ge=1, le=30)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    webhook_url: AnyHttpUrl | None = None
    metadata: dict[str, str] = Field(default_factory=dict, max_length=20)

    @model_validator(mode="after")
    def validate_mode(self) -> "GenerationRequest":
        if self.mode is GenerationMode.IMAGE_TO_VIDEO and self.image_url is None:
            raise ValueError("image_url é obrigatório para IMAGE_TO_VIDEO")
        if self.mode is not GenerationMode.IMAGE_TO_VIDEO and self.image_url is not None:
            raise ValueError("image_url só pode ser usado com IMAGE_TO_VIDEO")
        if self.mode is GenerationMode.TEXT_TO_IMAGE and self.duration_seconds is not None:
            raise ValueError("duration_seconds só pode ser usado para geração de vídeo")
        if self.mode is not GenerationMode.TEXT_TO_IMAGE and self.duration_seconds is None:
            self.duration_seconds = 5
        return self


class AssetResponse(BaseModel):
    asset_id: str
    url: str
    mime_type: str
    size_bytes: int


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: Any | None = None


class GenerationTask(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    task_id: str
    status: TaskStatus
    mode: GenerationMode
    prompt: str
    model: str | None = None
    progress: int = Field(default=0, ge=0, le=100)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    asset: AssetResponse | None = None
    error: ErrorResponse | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class PaginatedTasks(BaseModel):
    data: list[GenerationTask]
    pagination: dict[str, int]


class HealthResponse(BaseModel):
    status: str
    provider: str
    version: str


class ModelInfo(BaseModel):
    id: str
    media_types: list[str]
    modes: list[GenerationMode]
    supports_audio: bool = False


class ModelsResponse(BaseModel):
    data: list[ModelInfo]


class WebhookEvent(BaseModel):
    event: str
    task: GenerationTask
    delivered_at: datetime = Field(default_factory=utc_now)
