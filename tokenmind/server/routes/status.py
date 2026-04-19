"""Status API endpoint."""

from __future__ import annotations

from pydantic import BaseModel

from fastapi import APIRouter, Depends

router = APIRouter(prefix="/api", tags=["status"])


class StatusResponse(BaseModel):
    """Response model for status endpoint."""

    status: str
    version: str
    active_connections: int = 0
    channels: list[str] = []


def get_chat_service():
    """Get chat service dependency."""
    from tokenmind.server.dependencies import get_chat_service
    return get_chat_service()


def get_connection_manager():
    """Get connection manager dependency."""
    from tokenmind.server.dependencies import get_connection_manager
    return get_connection_manager()


@router.get("/status", response_model=StatusResponse)
async def get_status(
    service=Depends(get_chat_service),
    conn_manager=Depends(get_connection_manager),
):
    """Get the current status of the gateway."""
    from tokenmind.server import __version__

    return StatusResponse(
        status="running",
        version=__version__,
        active_connections=len(conn_manager.get_session_keys()),
        channels=["web"],
    )
