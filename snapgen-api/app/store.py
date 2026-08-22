from __future__ import annotations

import asyncio
from pathlib import Path
from typing import BinaryIO

from app.schemas import GenerationTask, TaskStatus


class TaskStore:
    """In-memory task index plus filesystem asset storage for the MVP.

    Replace the task index with Redis/PostgreSQL and the filesystem with object
    storage before deploying multiple API instances.
    """

    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._tasks: dict[str, GenerationTask] = {}
        self._lock = asyncio.Lock()

    async def create(self, task: GenerationTask) -> GenerationTask:
        async with self._lock:
            self._tasks[task.task_id] = task
            return task

    async def get(self, task_id: str) -> GenerationTask | None:
        async with self._lock:
            return self._tasks.get(task_id)

    async def update(self, task: GenerationTask) -> GenerationTask:
        async with self._lock:
            self._tasks[task.task_id] = task
            return task

    async def list(
        self, page: int, page_size: int, status: TaskStatus | None = None
    ) -> tuple[list[GenerationTask], int]:
        async with self._lock:
            tasks = sorted(
                (
                    task
                    for task in self._tasks.values()
                    if status is None or task.status == status
                ),
                key=lambda item: item.created_at,
                reverse=True,
            )
            total = len(tasks)
            start = (page - 1) * page_size
            return tasks[start : start + page_size], total

    def asset_path(self, asset_id: str, extension: str) -> Path:
        return self.storage_dir / f"{asset_id}.{extension}"

    async def save_asset(self, asset_id: str, extension: str, content: bytes) -> Path:
        path = self.asset_path(asset_id, extension)
        await asyncio.to_thread(path.write_bytes, content)
        return path

    def open_asset(self, asset_id: str, extension: str) -> BinaryIO:
        return self.asset_path(asset_id, extension).open("rb")
