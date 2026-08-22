from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.schemas import GenerationRequest


@dataclass(slots=True)
class GeneratedAsset:
    content: bytes
    mime_type: str
    extension: str
    provider_job_id: str | None = None


class GenerationProvider(Protocol):
    name: str

    async def generate(self, request: GenerationRequest) -> GeneratedAsset:
        """Generate one asset and return its bytes.

        A production provider may instead submit a remote job and poll it here,
        keeping that provider-specific behavior behind this interface.
        """

    def models(self) -> list[dict[str, Any]]:
        ...
