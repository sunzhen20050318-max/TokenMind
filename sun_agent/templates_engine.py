"""Small Jinja2 wrapper for optional response and memory templates."""

from __future__ import annotations

from typing import Any

from jinja2 import Environment, StrictUndefined, TemplateError
from loguru import logger


class TemplateRenderer:
    """Render short inline Jinja2 templates with safe fallback behavior."""

    def __init__(self) -> None:
        self._env = Environment(
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=StrictUndefined,
        )

    def render(self, template: str | None, **context: Any) -> str | None:
        """Render a template or return None when disabled / invalid."""
        if not template or not template.strip():
            return None
        try:
            rendered = self._env.from_string(template).render(**context)
        except TemplateError as exc:
            logger.warning("Template render failed: {}", exc)
            return None
        rendered = rendered.strip()
        return rendered or None
