"""API routes for sun_agent Web UI."""

from sun_agent.server.routes.chat import router as chat_router
from sun_agent.server.routes.config import router as config_router
from sun_agent.server.routes.sessions import router as sessions_router
from sun_agent.server.routes.status import router as status_router

__all__ = ["chat_router", "config_router", "sessions_router", "status_router"]
