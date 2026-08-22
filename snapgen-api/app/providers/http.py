from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.config import Settings
from app.providers.base import GeneratedAsset
from app.schemas import GenerationMode, GenerationRequest


class HttpProvider:
    """Adapter for a provider with a small, normalized HTTP contract.

    POST {base_url}/generations with the generation request. The provider may
    return an asset URL immediately or a job/status URL that becomes complete.
    """

    name = "http"

    def __init__(self, settings: Settings) -> None:
        if not settings.provider_base_url:
            raise ValueError("SNAPGEN_PROVIDER_BASE_URL é obrigatório para o provedor http")
        self.base_url = settings.provider_base_url.rstrip("/")
        self.timeout = settings.provider_timeout_seconds
        self.headers = (
            {"Authorization": f"Bearer {settings.provider_api_key}"}
            if settings.provider_api_key
            else {}
        )

    async def generate(self, request: GenerationRequest) -> GeneratedAsset:
        payload = request.model_dump(mode="json", exclude_none=True)
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            response = await client.post(f"{self.base_url}/generations", json=payload)
            response.raise_for_status()
            body = self._json_object(response)
            body = await self._wait_for_completion(client, body)
            asset_url = self._required_string(body, "asset_url", fallback="url")
            asset_response = await client.get(asset_url)
            asset_response.raise_for_status()
            mime_type = asset_response.headers.get("content-type", "application/octet-stream").split(";")[0]
            extension = self._extension_for(mime_type)
            return GeneratedAsset(
                content=asset_response.content,
                mime_type=mime_type,
                extension=extension,
                provider_job_id=self._optional_string(body, "id"),
            )

    async def _wait_for_completion(
        self, client: httpx.AsyncClient, body: dict[str, Any]
    ) -> dict[str, Any]:
        status_url = body.get("status_url")
        if not isinstance(status_url, str):
            return body

        for _ in range(120):
            status_response = await client.get(status_url)
            status_response.raise_for_status()
            status_body = self._json_object(status_response)
            status = str(status_body.get("status", "")).upper()
            if status in {"FAILED", "ERROR", "CANCELED"}:
                raise RuntimeError(str(status_body.get("error", "O provedor falhou")))
            if status in {"COMPLETED", "SUCCEEDED", "SUCCESS"} and (
                status_body.get("asset_url") or status_body.get("url")
            ):
                return status_body
            await asyncio.sleep(1)
        raise TimeoutError("O provedor não concluiu a geração no tempo esperado")

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError("O provedor retornou JSON inválido") from exc
        if not isinstance(body, dict):
            raise RuntimeError("O provedor retornou um objeto inválido")
        return body

    @staticmethod
    def _required_string(body: dict[str, Any], key: str, fallback: str) -> str:
        value = body.get(key) or body.get(fallback)
        if not isinstance(value, str) or not value:
            raise RuntimeError("O provedor não retornou a URL do ativo")
        return value

    @staticmethod
    def _optional_string(body: dict[str, Any], key: str) -> str | None:
        value = body.get(key)
        return value if isinstance(value, str) else None

    @staticmethod
    def _extension_for(mime_type: str) -> str:
        return {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/webp": "webp",
            "image/svg+xml": "svg",
            "video/mp4": "mp4",
            "video/webm": "webm",
        }.get(mime_type, "bin")

    def models(self) -> list[dict[str, object]]:
        return [
            {
                "id": "provider-managed",
                "media_types": ["image/*", "video/*"],
                "modes": [
                    GenerationMode.TEXT_TO_IMAGE,
                    GenerationMode.TEXT_TO_VIDEO,
                    GenerationMode.IMAGE_TO_VIDEO,
                ],
                "supports_audio": False,
            }
        ]
