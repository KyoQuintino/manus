from __future__ import annotations

import asyncio

import httpx
import pytest

from app.main import app


@pytest.mark.anyio
async def test_health_and_models() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/health")
        models = await client.get("/v1/models")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert {item["id"] for item in models.json()["data"]} == {
        "mock-image-v1",
        "mock-video-v1",
    }


@pytest.mark.anyio
async def test_text_to_image_completes_and_asset_is_downloadable() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/generations",
            json={"mode": "TEXT_TO_IMAGE", "prompt": "um pôr do sol minimalista"},
        )
        assert response.status_code == 202
        task_id = response.json()["task_id"]

        task = None
        for _ in range(30):
            task = await client.get(f"/v1/generations/{task_id}")
            if task.json()["status"] in {"COMPLETED", "FAILED"}:
                break
            await asyncio.sleep(0.05)

        assert task is not None
        assert task.json()["status"] == "COMPLETED"
        asset = await client.get(task.json()["asset"]["url"])
        assert asset.status_code == 200
        assert asset.headers["content-type"].startswith("image/svg+xml")
        assert b"snapgen.ai" in asset.content


@pytest.mark.anyio
async def test_both_video_modes_are_accepted() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        text_video = await client.post(
            "/v1/generations",
            json={
                "mode": "TEXT_TO_VIDEO",
                "prompt": "uma esfera azul flutuando",
                "duration_seconds": 1,
            },
        )
        image_video = await client.post(
            "/v1/generations",
            json={
                "mode": "IMAGE_TO_VIDEO",
                "prompt": "movimento de câmera suave",
                "image_url": "https://example.com/reference.png",
                "duration_seconds": 1,
            },
        )

    assert text_video.status_code == 202
    assert image_video.status_code == 202
    assert text_video.json()["mode"] == "TEXT_TO_VIDEO"
    assert image_video.json()["mode"] == "IMAGE_TO_VIDEO"


@pytest.mark.anyio
async def test_image_to_video_requires_image_url() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/generations",
            json={"mode": "IMAGE_TO_VIDEO", "prompt": "animar"},
        )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_video_generation_produces_mp4_asset() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/generations",
            json={
                "mode": "TEXT_TO_VIDEO",
                "prompt": "uma paisagem abstrata",
                "duration_seconds": 1,
            },
        )
        task_id = response.json()["task_id"]
        final_task = None
        for _ in range(40):
            candidate = await client.get(f"/v1/generations/{task_id}")
            if candidate.json()["status"] in {"COMPLETED", "FAILED"}:
                final_task = candidate.json()
                break
            await asyncio.sleep(0.1)

        assert final_task is not None
        assert final_task["status"] == "COMPLETED"
        asset = await client.get(final_task["asset"]["url"])
        assert asset.status_code == 200
        assert asset.headers["content-type"].startswith("video/mp4")
        assert b"ftyp" in asset.content[:16]


@pytest.mark.anyio
async def test_asset_path_traversal_is_rejected() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/assets/../../etc/passwd")

    assert response.status_code in {404, 307}
