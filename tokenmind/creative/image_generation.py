"""Image generation helpers for creative capabilities."""

from __future__ import annotations

import base64
import uuid
from dataclasses import dataclass
from math import gcd
from pathlib import Path
from typing import Any

import httpx
from openai import AsyncOpenAI

from tokenmind.config.schema import CreativeCapabilityConfig
from tokenmind.providers.registry import find_by_name
from tokenmind.utils.helpers import detect_image_mime

_DEFAULT_IMAGE_MODELS: dict[str, str] = {
    "minimax": "image-01",
    "openai": "gpt-image-1",
}


@dataclass(frozen=True)
class GeneratedImageResult:
    """One generated image payload ready to be attached to a reply."""

    filename: str
    mime_type: str
    data: bytes
    model: str
    provider: str
    revised_prompt: str | None = None


class ImageGenerationService:
    """Generate an image using the configured creative image capability."""

    def __init__(self, capability: CreativeCapabilityConfig):
        self._capability = capability

    @property
    def provider(self) -> str:
        return (self._capability.provider or "").strip()

    @property
    def model(self) -> str:
        configured = (self._capability.model or "").strip()
        if configured:
            return configured
        return _DEFAULT_IMAGE_MODELS.get(self.provider, "gpt-image-1")

    @property
    def api_base(self) -> str | None:
        configured = (self._capability.api_base or "").strip()
        if configured:
            return configured
        spec = find_by_name(self.provider)
        return spec.default_api_base if spec and spec.default_api_base else None

    @property
    def extra_headers(self) -> dict[str, str]:
        return dict(self._capability.extra_headers or {})

    @classmethod
    def is_configured(cls, capability: CreativeCapabilityConfig | None) -> bool:
        """Return True when the image capability has enough data to be used."""
        if capability is None or not capability.enabled:
            return False
        provider = (capability.provider or "").strip()
        if not provider:
            return False
        api_key = (capability.api_key or "").strip()
        spec = find_by_name(provider)
        return bool(api_key or (spec and (spec.is_local or spec.is_direct)))

    async def generate(
        self,
        prompt: str,
        *,
        size: str | None = None,
        quality: str | None = None,
        background: str | None = None,
        reference_image_paths: list[str] | None = None,
        reference_type: str = "character",
    ) -> GeneratedImageResult:
        """Generate one image from text."""
        if not prompt.strip():
            raise ValueError("Prompt cannot be empty")

        if self.provider == "minimax":
            return await self._generate_minimax(
                prompt=prompt,
                size=size,
                quality=quality,
                reference_image_paths=reference_image_paths,
                reference_type=reference_type,
            )
        return await self._generate_openai_compat(
            prompt=prompt,
            size=size,
            quality=quality,
            background=background,
        )

    async def _generate_openai_compat(
        self,
        *,
        prompt: str,
        size: str | None,
        quality: str | None,
        background: str | None,
    ) -> GeneratedImageResult:
        spec = find_by_name(self.provider)
        client_kwargs: dict[str, Any] = {
            "api_key": (self._capability.api_key or "").strip()
            or ("no-key" if spec and (spec.is_local or spec.is_direct) else "missing-key"),
            "default_headers": self.extra_headers or None,
        }
        if self.api_base:
            client_kwargs["base_url"] = self.api_base

        client = AsyncOpenAI(**client_kwargs)
        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "response_format": "b64_json",
        }
        if size:
            request_kwargs["size"] = size
        if quality:
            request_kwargs["quality"] = quality
        if background:
            request_kwargs["background"] = background

        response = await client.images.generate(**request_kwargs)
        images = getattr(response, "data", None) or []
        if not images:
            raise RuntimeError("Image API returned no images")

        item = images[0]
        if getattr(item, "b64_json", None):
            payload = base64.b64decode(item.b64_json)
        elif getattr(item, "url", None):
            payload = await self._download_bytes(item.url)
        else:
            raise RuntimeError("Image API response did not include b64_json or url")

        output_format = getattr(response, "output_format", None) or "png"
        return GeneratedImageResult(
            filename=f"generated-image-{uuid.uuid4().hex[:8]}.{output_format}",
            mime_type=_mime_for_format(output_format),
            data=payload,
            model=self.model,
            provider=self.provider,
            revised_prompt=getattr(item, "revised_prompt", None),
        )

    async def _generate_minimax(
        self,
        *,
        prompt: str,
        size: str | None,
        quality: str | None,
        reference_image_paths: list[str] | None,
        reference_type: str,
    ) -> GeneratedImageResult:
        endpoint = _resolve_minimax_endpoint(self.api_base)
        headers = {"Authorization": f"Bearer {(self._capability.api_key or '').strip()}"}
        headers.update(self.extra_headers)
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "response_format": "base64",
            "aspect_ratio": _size_to_aspect_ratio(size),
        }
        if quality:
            payload["quality"] = quality
        if reference_image_paths:
            payload["subject_reference"] = _build_subject_reference(
                reference_image_paths,
                reference_type=reference_type,
            )

        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        images = ((data.get("data") or {}).get("image_base64")) or []
        if not images:
            raise RuntimeError("MiniMax image API returned no images")

        return GeneratedImageResult(
            filename=f"generated-image-{uuid.uuid4().hex[:8]}.jpeg",
            mime_type="image/jpeg",
            data=base64.b64decode(images[0]),
            model=self.model,
            provider=self.provider,
        )

    async def _download_bytes(self, url: str) -> bytes:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            return response.content


def _resolve_minimax_endpoint(api_base: str | None) -> str:
    """Resolve the MiniMax native image-generation endpoint."""
    base = (api_base or "https://api.minimax.io/v1").rstrip("/")
    if base.endswith("/image_generation"):
        return base
    return f"{base}/image_generation"


def _size_to_aspect_ratio(size: str | None) -> str:
    """Map a WxH size string to a simple aspect ratio for MiniMax."""
    if not size or "x" not in size:
        return "1:1"
    raw_width, raw_height = size.lower().split("x", 1)
    try:
        width = int(raw_width)
        height = int(raw_height)
    except ValueError:
        return "1:1"
    if width <= 0 or height <= 0:
        return "1:1"
    factor = gcd(width, height)
    return f"{width // factor}:{height // factor}"


def _mime_for_format(output_format: str) -> str:
    normalized = output_format.lower()
    if normalized in {"jpg", "jpeg"}:
        return "image/jpeg"
    if normalized == "webp":
        return "image/webp"
    return "image/png"


def _build_subject_reference(reference_image_paths: list[str], *, reference_type: str) -> list[dict[str, str]]:
    """Build MiniMax subject_reference payload entries from local paths or remote URLs."""
    references: list[dict[str, str]] = []
    for item in reference_image_paths:
        source = item.strip()
        if not source:
            continue
        if source.startswith(("http://", "https://", "data:")):
            image_file = source
        else:
            path = Path(source)
            if not path.is_file():
                continue
            raw = path.read_bytes()
            mime = detect_image_mime(raw) or "image/png"
            image_file = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
        references.append({"type": reference_type, "image_file": image_file})
    return references
