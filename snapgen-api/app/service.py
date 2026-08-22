from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import uuid
from dataclasses import replace
from datetime import datetime, timezone

import httpx

from app.config import Settings
from app.providers.base import GenerationProvider
from app.schemas import (
    AssetResponse,
    ErrorResponse,
    GenerationRequest,
    GenerationTask,
    TaskStatus,
    WebhookEvent,
)
from app.store import TaskStore


class GenerationService:
    def __init__(self, store: TaskStore, provider: GenerationProvider, settings: Settings) -> None:
        self.store = store
        self.provider = provider
        self.settings = settings

    async def create_task(self, request: GenerationRequest) -> GenerationTask:
        task = GenerationTask(
            task_id=uuid.uuid4().hex,
            status=TaskStatus.QUEUED,
            mode=request.mode,
            prompt=request.prompt,
            model=request.model,
            metadata=request.metadata,
        )
        await self.store.create(task)
        asyncio.create_task(self._run_task(task.task_id, request))
        return task

    async def get_task(self, task_id: str) -> GenerationTask | None:
        return await self.store.get(task_id)

    async def list_tasks(
        self, page: int, page_size: int, status: TaskStatus | None = None
    ) -> tuple[list[GenerationTask], int]:
        return await self.store.list(page, page_size, status)

    async def cancel_task(self, task_id: str) -> GenerationTask | None:
        task = await self.store.get(task_id)
        if task is None:
            return None
        if task.status in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELED,
        }:
            return task
        updated = task.model_copy(
            update={
                "status": TaskStatus.CANCELED,
                "progress": 0,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        await self.store.update(updated)
        return updated

    async def _run_task(self, task_id: str, request: GenerationRequest) -> None:
        task = await self.store.get(task_id)
        if task is None:
            return
        processing = task.model_copy(
            update={
                "status": TaskStatus.PROCESSING,
                "progress": 10,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        await self.store.update(processing)
        try:
            generated = await self.provider.generate(request)
            current = await self.store.get(task_id)
            if current is None or current.status == TaskStatus.CANCELED:
                return
            asset_id = uuid.uuid4().hex
            await self.store.save_asset(asset_id, generated.extension, generated.content)
            asset = AssetResponse(
                asset_id=asset_id,
                url=f"{self.settings.public_base_url.rstrip('/')}/v1/assets/{asset_id}",
                mime_type=generated.mime_type,
                size_bytes=len(generated.content),
            )
            completed = current.model_copy(
                update={
                    "status": TaskStatus.COMPLETED,
                    "progress": 100,
                    "updated_at": datetime.now(timezone.utc),
                    "asset": asset,
                }
            )
            await self.store.update(completed)
            await self._send_webhook(request, "generation.completed", completed)
        except Exception as exc:  # Background jobs must always settle to a state.
            current = await self.store.get(task_id)
            if current is None or current.status == TaskStatus.CANCELED:
                return
            failed = current.model_copy(
                update={
                    "status": TaskStatus.FAILED,
                    "progress": 0,
                    "updated_at": datetime.now(timezone.utc),
                    "error": ErrorResponse(
                        code="GENERATION_FAILED",
                        message="A geração não pôde ser concluída.",
                        details=str(exc) if self.settings.environment != "production" else None,
                    ),
                }
            )
            await self.store.update(failed)
            await self._send_webhook(request, "generation.failed", failed)

    async def _send_webhook(
        self, request: GenerationRequest, event_name: str, task: GenerationTask
    ) -> None:
        if request.webhook_url is None:
            return
        event = WebhookEvent(event=event_name, task=task)
        body = event.model_dump_json().encode("utf-8")
        signature = hmac.new(
            self.settings.webhook_secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "X-Snapgen-Signature": f"sha256={signature}",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            for attempt in range(3):
                try:
                    response = await client.post(str(request.webhook_url), content=body, headers=headers)
                    response.raise_for_status()
                    return
                except httpx.HTTPError:
                    if attempt == 2:
                        return
                    await asyncio.sleep(2**attempt)
