"""FastAPI dependencies for TokenMind Web UI."""

from __future__ import annotations

from typing import Any

# Global instances - will be set during app startup
_chat_service: Any = None
_connection_manager: Any = None
_inbound_queue: Any = None
_cron_service: Any = None
_channel_manager: Any = None


def set_chat_service(service: Any) -> None:
    """Set the global chat service instance."""
    global _chat_service
    _chat_service = service


def get_chat_service() -> Any:
    """Get the global chat service instance."""
    return _chat_service


def set_connection_manager(manager: Any) -> None:
    """Set the global connection manager instance."""
    global _connection_manager
    _connection_manager = manager


def get_connection_manager() -> Any:
    """Get the global connection manager instance."""
    return _connection_manager


def set_inbound_queue(queue: Any) -> None:
    """Set the global inbound queue reference."""
    global _inbound_queue
    _inbound_queue = queue


def get_inbound_queue() -> Any:
    """Get the global inbound queue reference."""
    return _inbound_queue


def set_cron_service(service: Any) -> None:
    """Set the global cron service instance."""
    global _cron_service
    _cron_service = service


def get_cron_service() -> Any:
    """Get the global cron service instance."""
    return _cron_service


def set_channel_manager(manager: Any) -> None:
    """Set the global external channel manager instance."""
    global _channel_manager
    _channel_manager = manager


def get_channel_manager() -> Any:
    """Get the global external channel manager instance."""
    return _channel_manager


_usage_recorder: Any = None


def set_usage_recorder(recorder: Any) -> None:
    """Set the global token usage recorder instance."""
    global _usage_recorder
    _usage_recorder = recorder


def get_usage_recorder() -> Any:
    """Get the global token usage recorder instance."""
    return _usage_recorder


_opencli_service: Any = None


def set_opencli_service(service: Any) -> None:
    """Set the global OpenCLI service instance."""
    global _opencli_service
    _opencli_service = service


def get_opencli_service() -> Any:
    """Get the global OpenCLI service instance."""
    return _opencli_service


_site_registry: Any = None


def set_site_registry(registry: Any) -> None:
    """Set the global SiteRegistry instance (user-curated login state)."""
    global _site_registry
    _site_registry = registry


def get_site_registry() -> Any:
    """Get the global SiteRegistry instance."""
    return _site_registry


_app: Any = None


def set_app(app: Any) -> None:
    """Register the running FastAPI app instance so routes can reach
    app.state from outside the request scope (e.g. updating the cached
    auth_secret after settings rotate it)."""
    global _app
    _app = app


def get_app() -> Any:
    """Return the registered FastAPI app, or ``None`` before startup."""
    return _app
