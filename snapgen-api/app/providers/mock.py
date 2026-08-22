from __future__ import annotations

import asyncio
import hashlib
import subprocess
import tempfile
from pathlib import Path

from app.providers.base import GeneratedAsset
from app.schemas import GenerationMode, GenerationRequest


class MockProvider:
    """Deterministic local provider used for development and automated tests."""

    name = "mock"

    async def generate(self, request: GenerationRequest) -> GeneratedAsset:
        await asyncio.sleep(0.15)
        digest = hashlib.sha256(request.prompt.encode("utf-8")).hexdigest()
        color_a = f"#{digest[:6]}"
        color_b = f"#{digest[6:12]}"

        if request.mode is GenerationMode.TEXT_TO_IMAGE:
            svg = (
                '<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
                'viewBox="0 0 {width} {height}">'
                '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
                '<stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/>'
                '</linearGradient></defs><rect width="100%" height="100%" fill="url(#g)"/>'
                '<text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" '
                'font-family="sans-serif" font-size="32" fill="white">snapgen.ai</text></svg>'
            ).format(width=request.width, height=request.height, a=color_a, b=color_b)
            return GeneratedAsset(svg.encode("utf-8"), "image/svg+xml", "svg")

        # ffmpeg creates a small valid MP4 so clients can exercise the full
        # download flow. Real generation is supplied by a configured provider.
        with tempfile.TemporaryDirectory(prefix="snapgen-mock-") as temp_dir:
            output = Path(temp_dir) / "preview.mp4"
            duration = request.duration_seconds or 5
            command = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color_a}:s=640x360:r=24",
                "-t",
                str(min(duration, 5)),
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-y",
                str(output),
            ]
            process = await asyncio.to_thread(
                subprocess.run, command, capture_output=True, check=False
            )
            if process.returncode != 0 or not output.exists():
                raise RuntimeError("Não foi possível criar o vídeo de demonstração")
            return GeneratedAsset(output.read_bytes(), "video/mp4", "mp4")

    def models(self) -> list[dict[str, object]]:
        return [
            {
                "id": "mock-image-v1",
                "media_types": ["image/svg+xml"],
                "modes": [GenerationMode.TEXT_TO_IMAGE],
                "supports_audio": False,
            },
            {
                "id": "mock-video-v1",
                "media_types": ["video/mp4"],
                "modes": [GenerationMode.TEXT_TO_VIDEO, GenerationMode.IMAGE_TO_VIDEO],
                "supports_audio": False,
            },
        ]
