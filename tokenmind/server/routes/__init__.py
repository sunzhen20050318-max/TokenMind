"""API routes for TokenMind Web UI."""

from tokenmind.server.routes.assets import router as assets_router
from tokenmind.server.routes.chat import router as chat_router
from tokenmind.server.routes.config import router as config_router
from tokenmind.server.routes.creative import router as creative_router
from tokenmind.server.routes.cron import router as cron_router
from tokenmind.server.routes.knowledge import router as knowledge_router
from tokenmind.server.routes.memory import router as memory_router
from tokenmind.server.routes.projects import router as projects_router
from tokenmind.server.routes.sessions import router as sessions_router
from tokenmind.server.routes.skills import router as skills_router
from tokenmind.server.routes.status import router as status_router
from tokenmind.server.routes.storage import router as storage_router
from tokenmind.server.routes.usage import router as usage_router

__all__ = [
    "assets_router",
    "chat_router",
    "config_router",
    "creative_router",
    "cron_router",
    "knowledge_router",
    "memory_router",
    "projects_router",
    "sessions_router",
    "skills_router",
    "status_router",
    "storage_router",
    "usage_router",
]
