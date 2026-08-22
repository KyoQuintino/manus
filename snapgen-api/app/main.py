from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse

from app.config import settings
from app.providers.http import HttpProvider
from app.providers.mock import MockProvider
from app.schemas import (
    ErrorResponse,
    GenerationMode,
    GenerationRequest,
    GenerationTask,
    HealthResponse,
    ModelInfo,
    ModelsResponse,
    PaginatedTasks,
    TaskStatus,
)
from app.service import GenerationService
from app.store import TaskStore


def build_provider():
    if settings.provider == "http":
        return HttpProvider(settings)
    if settings.provider != "mock":
        raise RuntimeError(f"Provedor desconhecido: {settings.provider}")
    return MockProvider()


store = TaskStore(settings.storage_dir)
provider = build_provider()
service = GenerationService(store, provider, settings)

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "API assíncrona para geração de imagens, texto-para-vídeo e "
        "imagem-para-vídeo."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)


async def authenticate(x_api_key: str | None = Header(default=None)) -> None:
    """Optional API-key guard: open in local development, protected when configured."""
    if settings.api_key and (
        x_api_key is None or not secrets.compare_digest(x_api_key, settings.api_key)
    ):
        raise HTTPException(
            status_code=401,
            detail={
                "code": "UNAUTHORIZED",
                "message": "X-API-Key ausente ou inválida.",
            },
        )


def not_found(task_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "TASK_NOT_FOUND", "message": f"Tarefa {task_id} não encontrada."},
    )


@app.get("/health", response_model=HealthResponse, tags=["Sistema"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok", provider=provider.name, version=settings.version)


@app.get("/v1/models", response_model=ModelsResponse, tags=["Geração"])
async def models(_: None = Depends(authenticate)) -> ModelsResponse:
    return ModelsResponse(data=[ModelInfo(**model) for model in provider.models()])


@app.post(
    "/v1/generations",
    response_model=GenerationTask,
    status_code=202,
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    tags=["Geração"],
)
async def create_generation(
    payload: GenerationRequest, _: None = Depends(authenticate)
) -> GenerationTask:
    return await service.create_task(payload)


@app.get("/v1/generations", response_model=PaginatedTasks, tags=["Geração"])
async def list_generations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: TaskStatus | None = Query(default=None),
    _: None = Depends(authenticate),
) -> PaginatedTasks:
    tasks, total = await service.list_tasks(page, page_size, status)
    return PaginatedTasks(
        data=tasks,
        pagination={
            "page": page,
            "pageSize": page_size,
            "totalItems": total,
            "totalPages": (total + page_size - 1) // page_size,
        },
    )


@app.get("/v1/generations/{task_id}", response_model=GenerationTask, tags=["Geração"])
async def get_generation(task_id: str, _: None = Depends(authenticate)) -> GenerationTask:
    task = await service.get_task(task_id)
    if task is None:
        raise not_found(task_id)
    return task


@app.post("/v1/generations/{task_id}/cancel", response_model=GenerationTask, tags=["Geração"])
async def cancel_generation(task_id: str, _: None = Depends(authenticate)) -> GenerationTask:
    task = await service.cancel_task(task_id)
    if task is None:
        raise not_found(task_id)
    return task


@app.get("/v1/assets/{asset_id}", response_class=FileResponse, tags=["Ativos"])
async def get_asset(asset_id: str, _: None = Depends(authenticate)) -> FileResponse:
    if len(asset_id) != 32 or any(character not in "0123456789abcdef" for character in asset_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "ASSET_NOT_FOUND", "message": "Ativo não encontrado."},
        )
    matches = list(Path(settings.storage_dir).glob(f"{asset_id}.*"))
    if len(matches) != 1 or not matches[0].is_file():
        raise HTTPException(
            status_code=404,
            detail={"code": "ASSET_NOT_FOUND", "message": "Ativo não encontrado."},
        )
    return FileResponse(matches[0])
