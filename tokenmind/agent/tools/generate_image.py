"""Tool for generating an image inside the current conversation."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from tokenmind.agent.tools.base import Tool
from tokenmind.creative.image_generation import ImageGenerationService
from tokenmind.server.attachments import AttachmentStore


class GenerateImageTool(Tool):
    """Generate an image and attach it to the current reply when possible."""

    def __init__(self, service: ImageGenerationService, store: AttachmentStore, retention: timedelta):
        self._service = service
        self._store = store
        self._retention = retention
        self._channel = ""
        self._chat_id = ""
        self._message_id: str | None = None
        self._delivered: list[dict[str, Any]] = []
        self._current_attachments: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "generate_image"

    @property
    def description(self) -> str:
        return (
            "Generate an image from a text prompt. Use this when the user asks you to draw, "
            "illustrate, design, render, create a poster, or make a visual. "
            "In web chat, generated images are automatically attached to the reply. "
            "Only use reference images when the user explicitly asks to reference or base the new image on an uploaded image."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed image prompt describing the scene, style, and important constraints.",
                },
                "size": {
                    "type": ["string", "null"],
                    "description": "Optional image size like 1024x1024, 1536x1024, or 1024x1536.",
                },
                "quality": {
                    "type": ["string", "null"],
                    "description": "Optional quality hint such as standard, hd, high, or auto.",
                },
                "background": {
                    "type": ["string", "null"],
                    "description": "Optional background hint such as auto, opaque, or transparent when supported.",
                },
                "reference_image_paths": {
                    "type": ["array", "null"],
                    "items": {"type": "string"},
                    "description": "Optional uploaded image paths to use as references, but only when the user explicitly asks to reference those images.",
                },
                "reference_type": {
                    "type": ["string", "null"],
                    "description": "Optional MiniMax reference type such as character or style.",
                },
            },
            "required": ["prompt"],
        }

    def set_context(self, channel: str, chat_id: str, message_id: str | None = None) -> None:
        self._channel = channel
        self._chat_id = chat_id
        self._message_id = message_id

    def start_turn(self) -> None:
        self._delivered = []
        self._current_attachments = []

    def set_available_attachments(self, attachments: list[dict[str, Any]] | None) -> None:
        self._current_attachments = list(attachments or [])

    @property
    def delivered(self) -> list[dict[str, Any]]:
        return list(self._delivered)

    async def execute(
        self,
        prompt: str,
        size: str | None = None,
        quality: str | None = None,
        background: str | None = None,
        reference_image_paths: list[str] | None = None,
        reference_type: str | None = None,
        **_: Any,
    ) -> str:
        if not self._chat_id:
            return "Error: generate_image is not available without an active conversation context."
        try:
            resolved_reference_paths = reference_image_paths
            if resolved_reference_paths is None and _has_explicit_reference_intent(prompt):
                auto_paths = [
                    str(item.get("path"))
                    for item in self._current_attachments
                    if item.get("is_image") and item.get("path")
                ]
                resolved_reference_paths = auto_paths or None
            result = await self._service.generate(
                prompt,
                size=size,
                quality=quality,
                background=background,
                reference_image_paths=resolved_reference_paths,
                reference_type=reference_type or "character",
            )
            ref = self._store.create_generated(
                self._chat_id,
                filename=result.filename,
                content=result.data,
                mime_type=result.mime_type,
                retention=self._retention,
                message_id=self._message_id,
            )
            self._delivered.append(ref)
            attachment = self._store.resolve(ref["id"]).to_dict()
            if self._channel == "web":
                return f"Generated image {ref['name']} and attached it to the current web reply."
            return f"Generated image saved to {attachment['storage_path']}."
        except Exception as exc:
            return f"Error generating image: {exc}"


_EXPLICIT_REFERENCE_PATTERNS = (
    r"参考这张图",
    r"参考这个图片",
    r"按这张图",
    r"按这个图片",
    r"基于这张图",
    r"基于这个图片",
    r"照着这张图",
    r"根据这张图",
    r"以这张图为参考",
    r"reference (this|the) image",
    r"based on (this|the) image",
    r"use (this|the) image as reference",
)


def _has_explicit_reference_intent(prompt: str) -> bool:
    """Return True when the prompt clearly asks to use an uploaded image as a reference."""
    normalized = prompt.strip().lower()
    if not normalized:
        return False
    return any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in _EXPLICIT_REFERENCE_PATTERNS)
