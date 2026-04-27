"""Tool for returning assistant-generated attachments in web chat."""

from __future__ import annotations

from contextvars import ContextVar
from datetime import timedelta
from typing import Any

from tokenmind.agent.tools.base import Tool
from tokenmind.server.attachments import AttachmentStore


# Per-asyncio-task context. The agent loop dispatches each session message into
# its own asyncio.Task (see AgentLoop.run), and asyncio.create_task copies the
# current context to the new task — so each in-flight session sees its own
# isolated turn-state instead of clobbering a shared singleton.
_channel_ctx: ContextVar[str] = ContextVar("deliver_attachment_channel", default="")
_chat_id_ctx: ContextVar[str] = ContextVar("deliver_attachment_chat_id", default="")
_message_id_ctx: ContextVar[str | None] = ContextVar(
    "deliver_attachment_message_id", default=None
)
_delivered_ctx: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "deliver_attachment_delivered", default=None
)


class DeliverAttachmentTool(Tool):
    """Create assistant attachment records for the current web session."""

    def __init__(self, store: AttachmentStore, retention: timedelta):
        self._store = store
        self._retention = retention

    @property
    def name(self) -> str:
        return "deliver_attachment"

    @property
    def description(self) -> str:
        return (
            "Attach a downloadable or previewable file to the current web chat reply. "
            "If the file already exists on disk, always use source_type=local_file with its exact path; "
            "do not read the file and resend it as inline_content. "
            "Use inline_content only for newly generated short text that does not already exist as a file."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source_type": {
                    "type": "string",
                    "enum": ["local_file", "remote_url", "inline_content"],
                    "description": "How the attachment source should be interpreted.",
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Existing local file path for source_type=local_file. "
                        "Required when attaching a file that was read, created, or found on disk."
                    ),
                },
                "url": {
                    "type": "string",
                    "description": "Remote URL for source_type=remote_url.",
                },
                "filename": {
                    "type": "string",
                    "description": "Target display filename. Required for inline_content and recommended elsewhere.",
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Inline text content for source_type=inline_content. "
                        "Do not use this for an existing local file; use path instead."
                    ),
                },
                "mime_type": {
                    "type": "string",
                    "description": "Optional MIME type override.",
                },
            },
            "required": ["source_type"],
        }

    def set_context(self, channel: str, chat_id: str, message_id: str | None = None) -> None:
        _channel_ctx.set(channel)
        _chat_id_ctx.set(chat_id)
        _message_id_ctx.set(message_id)

    def start_turn(self) -> None:
        # Allocate a fresh list per turn — never share across sessions.
        _delivered_ctx.set([])

    @property
    def delivered(self) -> list[dict[str, Any]]:
        bucket = _delivered_ctx.get()
        if bucket is None:
            return []
        return list(bucket)

    def _record(self, ref: dict[str, Any]) -> None:
        bucket = _delivered_ctx.get()
        if bucket is None:
            bucket = []
            _delivered_ctx.set(bucket)
        bucket.append(ref)

    @staticmethod
    def _is_blankish(value: Any) -> bool:
        if value is None:
            return True
        if not isinstance(value, str):
            return False
        return value.strip().lower() in {"", "null", "none"}

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        errors = super().validate_params(params)

        source_type = params.get("source_type")
        if source_type == "local_file" and self._is_blankish(params.get("path")):
            errors.append("local_file requires non-empty path")
        elif source_type == "remote_url" and self._is_blankish(params.get("url")):
            errors.append("remote_url requires non-empty url")
        elif source_type == "inline_content":
            if self._is_blankish(params.get("filename")):
                errors.append("inline_content requires a real filename")
            if params.get("content") is None:
                errors.append("inline_content requires content")
            elif isinstance(params.get("content"), str) and params["content"].strip().lower() in {"null", "none"}:
                errors.append("inline_content requires real content")
        return errors

    async def execute(
        self,
        source_type: str,
        path: str | None = None,
        url: str | None = None,
        filename: str | None = None,
        content: str | None = None,
        mime_type: str | None = None,
        **_: Any,
    ) -> str:
        channel = _channel_ctx.get()
        chat_id = _chat_id_ctx.get()
        message_id = _message_id_ctx.get()
        if channel != "web" or not chat_id:
            return "Error: deliver_attachment is only available in the current web chat."

        if source_type == "inline_content":
            if not filename or content is None:
                return "Error: inline_content requires filename and content"
            ref = self._store.create_generated(
                chat_id,
                filename=filename,
                content=content,
                mime_type=mime_type,
                retention=self._retention,
                message_id=message_id,
            )
            self._record(ref)
            return f"Prepared attachment {ref['name']}."

        if source_type == "local_file":
            if not path:
                return "Error: local_file requires path"
            ref = self._store.create_local(
                chat_id,
                source_path=path,
                retention=self._retention,
                message_id=message_id,
                attachment_name=filename,
            )
            self._record(ref)
            return f"Prepared attachment {ref['name']}."

        if source_type == "remote_url":
            if not url:
                return "Error: remote_url requires url"
            ref = self._store.create_remote(
                chat_id,
                source_url=url,
                retention=self._retention,
                message_id=message_id,
                filename=filename,
            )
            self._record(ref)
            return f"Prepared attachment {ref['name']}."

        return f"Error: unsupported source_type '{source_type}'"
