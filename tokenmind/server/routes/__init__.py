"""API routes for TokenMind Web UI."""

from tokenmind.server.routes.chat import router as chat_router
from tokenmind.server.routes.config import router as config_router
from tokenmind.server.routes.cron import router as cron_router
from tokenmind.server.routes.knowledge import router as knowledge_router
from tokenmind.server.routes.memory import router as memory_router
from tokenmind.server.routes.sessions import router as sessions_router
from tokenmind.server.routes.status import router as status_router
from tokenmind.server.routes.storage import router as storage_router

__all__ = [
    "chat_router",
    "config_router",
    "cron_router",
    "knowledge_router",
    "memory_router",
    "sessions_router",
    "status_router",
    "storage_router",
]
