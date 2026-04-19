"""Config API endpoints."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tokenmind.agent.tools.mcp import inspect_mcp_servers
from tokenmind.config.loader import load_config, save_config
from tokenmind.config.schema import MCPServerConfig

router = APIRouter(prefix="/api/config", tags=["config"])


class ProviderConfigUpdate(BaseModel):
    """Request model for updating a provider config."""

    api_key: str | None = None
    api_base: str | None = None
    extra_headers: dict[str, str] | None = None
    default_model: str | None = None


class DefaultsUpdate(BaseModel):
    """Request model for updating default agent config."""

    model: str | None = None
    provider: str | None = None


class AgentConfigUpdate(BaseModel):
    """Request model for updating agent defaults."""

    workspace: str | None = None
    model: str | None = None
    provider: str | None = None
    max_tokens: int | None = None
    context_window_tokens: int | None = None
    temperature: float | None = None
    max_tool_iterations: int | None = None
    reasoning_effort: str | None = None


class WebSearchConfigUpdate(BaseModel):
    """Partial update for web search tool configuration."""

    provider: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    max_results: int | None = None


class WebToolsConfigUpdate(BaseModel):
    """Partial update for web tool configuration."""

    proxy: str | None = None
    search: WebSearchConfigUpdate | None = None


class ExecToolConfigUpdate(BaseModel):
    """Partial update for exec tool configuration."""

    timeout: int | None = None
    path_append: str | None = None
    confirm_high_risk: bool | None = None
    approval_timeout_s: int | None = None


class UploadsConfigUpdate(BaseModel):
    """Partial update for upload storage policy."""

    max_file_mb: int | None = None
    max_total_mb: int | None = None
    retention_days: int | None = None
    cleanup_interval_hours: int | None = None


class KnowledgeConfigUpdate(BaseModel):
    """Partial update for knowledge base configuration."""

    vector_backend: str | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    top_k: int | None = None
    embedding_model: str | None = None
    embedding_api_key: str | None = None
    embedding_api_base: str | None = None
    rerank_model: str | None = None
    rerank_api_key: str | None = None
    rerank_api_base: str | None = None
    rerank_top_n: int | None = None


class ToolsConfigUpdate(BaseModel):
    """Partial update for tool configuration."""

    web: WebToolsConfigUpdate | None = None
    exec: ExecToolConfigUpdate | None = None
    uploads: UploadsConfigUpdate | None = None
    knowledge: KnowledgeConfigUpdate | None = None
    audit_enabled: bool | None = None
    restrict_to_workspace: bool | None = None


class ChannelsConfigUpdate(BaseModel):
    """Partial update for runtime channel behavior."""

    send_progress: bool | None = None
    send_tool_hints: bool | None = None


class HeartbeatConfigUpdate(BaseModel):
    """Partial update for heartbeat configuration."""

    enabled: bool | None = None
    interval_s: int | None = None


class GatewayConfigUpdate(BaseModel):
    """Partial update for gateway configuration."""

    host: str | None = None
    port: int | None = None
    heartbeat: HeartbeatConfigUpdate | None = None


class RuntimeConfigUpdate(BaseModel):
    """Partial update for runtime configuration."""

    channels: ChannelsConfigUpdate | None = None
    gateway: GatewayConfigUpdate | None = None


class TemplatesConfigUpdate(BaseModel):
    """Partial update for optional Jinja2 templates."""

    response: str | None = None
    memory_system: str | None = None
    memory_prompt: str | None = None


class MCPServerConfigUpdate(BaseModel):
    """Create or update an MCP server configuration."""

    type: Literal["stdio", "sse", "streamableHttp"] | None = None
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    tool_timeout: int | None = None
    enabled_tools: list[str] | None = None


class ConfigResponse(BaseModel):
    """Response model for GET /api/config."""

    providers: dict[str, dict[str, Any]]
    defaults: dict[str, Any]
    agent: dict[str, Any]
    tools: dict[str, Any]
    runtime: dict[str, Any]
    templates: dict[str, Any]


class MCPDiscoveredToolResponse(BaseModel):
    """Single tool discovered from a live MCP server probe."""

    name: str
    wrapped_name: str
    description: str
    enabled: bool


class MCPServerToolsResponse(BaseModel):
    """Live MCP server probe result."""

    status: Literal["connected", "error"]
    transport_type: str | None = None
    tool_count: int
    enabled_count: int
    tools: list[MCPDiscoveredToolResponse]
    error: str | None = None


class MCPCatalogResponse(BaseModel):
    """Response model for GET /api/config/mcp-tools."""

    servers: dict[str, MCPServerToolsResponse]


def _mask_api_key(api_key: str | None) -> str:
    """Mask an API key, showing only the last 4 characters."""
    if not api_key:
        return ""
    if len(api_key) <= 4:
        return "****"
    return "****" + api_key[-4:]


def _provider_config_to_dict(provider_config: object) -> dict[str, Any]:
    """Convert a provider config to dict with masked secrets."""
    return {
        "api_key": _mask_api_key(getattr(provider_config, "api_key", "")),
        "api_base": getattr(provider_config, "api_base", None),
        "extra_headers": getattr(provider_config, "extra_headers", None),
        "default_model": getattr(provider_config, "default_model", None),
    }


def _web_search_to_dict(search_config: object) -> dict[str, Any]:
    """Convert a web search config to serializable dict with masked secret."""
    return {
        "provider": getattr(search_config, "provider", None),
        "api_key": _mask_api_key(getattr(search_config, "api_key", "")),
        "base_url": getattr(search_config, "base_url", None),
        "max_results": getattr(search_config, "max_results", None),
    }


def _mcp_server_to_dict(server_config: MCPServerConfig) -> dict[str, Any]:
    """Convert an MCP server config to a plain dict."""
    return {
        "type": server_config.type,
        "command": server_config.command,
        "args": server_config.args,
        "env": server_config.env,
        "url": server_config.url,
        "headers": server_config.headers,
        "tool_timeout": server_config.tool_timeout,
        "enabled_tools": server_config.enabled_tools,
    }


def _build_config_response() -> ConfigResponse:
    """Load and serialize the current config for the frontend."""
    config = load_config()

    providers_dict: dict[str, dict[str, Any]] = {}
    for provider_name in type(config.providers).model_fields:
        provider_config = getattr(config.providers, provider_name, None)
        if provider_config is not None:
            providers_dict[provider_name] = _provider_config_to_dict(provider_config)

    agent_dict = config.agents.defaults.model_dump()
    tools_dict = {
        "web": {
            "proxy": config.tools.web.proxy,
            "search": _web_search_to_dict(config.tools.web.search),
        },
        "exec": config.tools.exec.model_dump(),
        "uploads": config.tools.uploads.model_dump(),
        "knowledge": {
            **config.tools.knowledge.model_dump(),
            "embedding_api_key": _mask_api_key(config.tools.knowledge.embedding_api_key),
            "rerank_api_key": _mask_api_key(config.tools.knowledge.rerank_api_key),
        },
        "audit_enabled": config.tools.audit_enabled,
        "restrict_to_workspace": config.tools.restrict_to_workspace,
        "mcp_servers": {
            name: _mcp_server_to_dict(server)
            for name, server in config.tools.mcp_servers.items()
        },
    }
    runtime_dict = {
        "channels": {
            "send_progress": config.channels.send_progress,
            "send_tool_hints": config.channels.send_tool_hints,
        },
        "gateway": {
            "host": config.gateway.host,
            "port": config.gateway.port,
            "heartbeat": config.gateway.heartbeat.model_dump(),
        },
    }
    templates_dict = config.templates.model_dump()

    return ConfigResponse(
        providers=providers_dict,
        defaults=agent_dict.copy(),
        agent=agent_dict,
        tools=tools_dict,
        runtime=runtime_dict,
        templates=templates_dict,
    )


@router.get("", response_model=ConfigResponse)
async def get_config():
    """Get the current configuration with masked API keys."""
    try:
        return _build_config_response()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load config: {e}") from e


@router.get("/mcp-tools", response_model=MCPCatalogResponse)
async def get_mcp_tools():
    """Probe configured MCP servers and return their discovered tools."""
    try:
        config = load_config()
        return {
            "servers": await inspect_mcp_servers(config.tools.mcp_servers),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to inspect MCP tools: {e}") from e


@router.put("/providers/{provider}")
async def update_provider_config(provider: str, update: ProviderConfigUpdate):
    """Update a specific provider's configuration."""
    try:
        config = load_config()

        if not hasattr(config.providers, provider):
            raise HTTPException(status_code=404, detail=f"Provider '{provider}' not found")

        provider_config = getattr(config.providers, provider)

        if "api_key" in update.model_fields_set:
            provider_config.api_key = update.api_key
        if "api_base" in update.model_fields_set:
            provider_config.api_base = update.api_base
        if "extra_headers" in update.model_fields_set:
            provider_config.extra_headers = update.extra_headers or None
        if "default_model" in update.model_fields_set:
            provider_config.default_model = update.default_model or None

        save_config(config)

        return {
            "success": True,
            "provider": provider,
            "config": _provider_config_to_dict(provider_config),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update provider: {e}") from e


@router.put("/defaults")
async def update_defaults(update: DefaultsUpdate):
    """Update the default agent configuration."""
    try:
        config = load_config()

        if update.model is not None:
            config.agents.defaults.model = update.model
        if update.provider is not None:
            config.agents.defaults.provider = update.provider

        save_config(config)

        return {
            "success": True,
            "defaults": {
                "model": config.agents.defaults.model,
                "provider": config.agents.defaults.provider,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update defaults: {e}") from e


@router.put("/agent")
async def update_agent_config(update: AgentConfigUpdate):
    """Update agent defaults beyond provider/model selection."""
    try:
        config = load_config()
        defaults = config.agents.defaults

        if "workspace" in update.model_fields_set:
            defaults.workspace = update.workspace
        if "model" in update.model_fields_set:
            defaults.model = update.model
        if "provider" in update.model_fields_set:
            defaults.provider = update.provider
        if "max_tokens" in update.model_fields_set:
            defaults.max_tokens = update.max_tokens
        if "context_window_tokens" in update.model_fields_set:
            defaults.context_window_tokens = update.context_window_tokens
        if "temperature" in update.model_fields_set:
            defaults.temperature = update.temperature
        if "max_tool_iterations" in update.model_fields_set:
            defaults.max_tool_iterations = update.max_tool_iterations
        if "reasoning_effort" in update.model_fields_set:
            defaults.reasoning_effort = update.reasoning_effort or None

        save_config(config)

        return {
            "success": True,
            "agent": defaults.model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update agent config: {e}") from e


@router.put("/tools")
async def update_tools_config(update: ToolsConfigUpdate):
    """Update tool configuration excluding MCP server definitions."""
    try:
        config = load_config()

        if "audit_enabled" in update.model_fields_set:
            config.tools.audit_enabled = bool(update.audit_enabled)

        if "restrict_to_workspace" in update.model_fields_set:
            config.tools.restrict_to_workspace = update.restrict_to_workspace

        if update.web is not None:
            if "proxy" in update.web.model_fields_set:
                config.tools.web.proxy = update.web.proxy or None
            if update.web.search is not None:
                search = config.tools.web.search
                if "provider" in update.web.search.model_fields_set:
                    search.provider = update.web.search.provider
                if "api_key" in update.web.search.model_fields_set:
                    search.api_key = update.web.search.api_key
                if "base_url" in update.web.search.model_fields_set:
                    search.base_url = update.web.search.base_url or ""
                if "max_results" in update.web.search.model_fields_set:
                    search.max_results = update.web.search.max_results

        if update.exec is not None:
            if "timeout" in update.exec.model_fields_set:
                config.tools.exec.timeout = update.exec.timeout
            if "path_append" in update.exec.model_fields_set:
                config.tools.exec.path_append = update.exec.path_append
            if "confirm_high_risk" in update.exec.model_fields_set:
                config.tools.exec.confirm_high_risk = bool(update.exec.confirm_high_risk)
            if "approval_timeout_s" in update.exec.model_fields_set:
                config.tools.exec.approval_timeout_s = update.exec.approval_timeout_s

        if update.uploads is not None:
            uploads = config.tools.uploads
            if "max_file_mb" in update.uploads.model_fields_set:
                uploads.max_file_mb = update.uploads.max_file_mb
            if "max_total_mb" in update.uploads.model_fields_set:
                uploads.max_total_mb = update.uploads.max_total_mb
            if "retention_days" in update.uploads.model_fields_set:
                uploads.retention_days = update.uploads.retention_days
            if "cleanup_interval_hours" in update.uploads.model_fields_set:
                uploads.cleanup_interval_hours = update.uploads.cleanup_interval_hours

        if update.knowledge is not None:
            knowledge = config.tools.knowledge
            if "vector_backend" in update.knowledge.model_fields_set:
                knowledge.vector_backend = update.knowledge.vector_backend or "sqlite"
            if "chunk_size" in update.knowledge.model_fields_set:
                knowledge.chunk_size = update.knowledge.chunk_size
            if "chunk_overlap" in update.knowledge.model_fields_set:
                knowledge.chunk_overlap = update.knowledge.chunk_overlap
            if "top_k" in update.knowledge.model_fields_set:
                knowledge.top_k = update.knowledge.top_k
            if "embedding_model" in update.knowledge.model_fields_set:
                knowledge.embedding_model = update.knowledge.embedding_model or ""
            if "embedding_api_key" in update.knowledge.model_fields_set:
                knowledge.embedding_api_key = update.knowledge.embedding_api_key or ""
            if "embedding_api_base" in update.knowledge.model_fields_set:
                knowledge.embedding_api_base = update.knowledge.embedding_api_base or None
            if "rerank_model" in update.knowledge.model_fields_set:
                knowledge.rerank_model = update.knowledge.rerank_model or ""
            if "rerank_api_key" in update.knowledge.model_fields_set:
                knowledge.rerank_api_key = update.knowledge.rerank_api_key or ""
            if "rerank_api_base" in update.knowledge.model_fields_set:
                knowledge.rerank_api_base = update.knowledge.rerank_api_base or None
            if "rerank_top_n" in update.knowledge.model_fields_set:
                knowledge.rerank_top_n = update.knowledge.rerank_top_n

        save_config(config)

        return {
            "success": True,
            "tools": _build_config_response().tools,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update tools config: {e}") from e


@router.put("/runtime")
async def update_runtime_config(update: RuntimeConfigUpdate):
    """Update channel and gateway runtime configuration."""
    try:
        config = load_config()

        if update.channels is not None:
            if "send_progress" in update.channels.model_fields_set:
                config.channels.send_progress = update.channels.send_progress
            if "send_tool_hints" in update.channels.model_fields_set:
                config.channels.send_tool_hints = update.channels.send_tool_hints

        if update.gateway is not None:
            if "host" in update.gateway.model_fields_set:
                config.gateway.host = update.gateway.host
            if "port" in update.gateway.model_fields_set:
                config.gateway.port = update.gateway.port
            if update.gateway.heartbeat is not None:
                if "enabled" in update.gateway.heartbeat.model_fields_set:
                    config.gateway.heartbeat.enabled = update.gateway.heartbeat.enabled
                if "interval_s" in update.gateway.heartbeat.model_fields_set:
                    config.gateway.heartbeat.interval_s = update.gateway.heartbeat.interval_s

        save_config(config)

        return {
            "success": True,
            "runtime": _build_config_response().runtime,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update runtime config: {e}") from e


@router.put("/templates")
async def update_templates_config(update: TemplatesConfigUpdate):
    """Update optional Jinja2 templates for responses and memory flows."""
    try:
        config = load_config()

        if "response" in update.model_fields_set:
            config.templates.response = update.response or None
        if "memory_system" in update.model_fields_set:
            config.templates.memory_system = update.memory_system or None
        if "memory_prompt" in update.model_fields_set:
            config.templates.memory_prompt = update.memory_prompt or None

        save_config(config)

        return {
            "success": True,
            "templates": config.templates.model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update templates config: {e}") from e


@router.put("/mcp-servers/{server_name}")
async def upsert_mcp_server(server_name: str, update: MCPServerConfigUpdate):
    """Create or update an MCP server definition."""
    normalized_name = server_name.strip()
    if not normalized_name:
        raise HTTPException(status_code=400, detail="Server name cannot be empty")

    try:
        config = load_config()
        server = config.tools.mcp_servers.get(normalized_name, MCPServerConfig())

        if "type" in update.model_fields_set:
            server.type = update.type
        if "command" in update.model_fields_set:
            server.command = update.command
        if "args" in update.model_fields_set:
            server.args = update.args
        if "env" in update.model_fields_set:
            server.env = update.env
        if "url" in update.model_fields_set:
            server.url = update.url
        if "headers" in update.model_fields_set:
            server.headers = update.headers
        if "tool_timeout" in update.model_fields_set:
            server.tool_timeout = update.tool_timeout
        if "enabled_tools" in update.model_fields_set:
            server.enabled_tools = update.enabled_tools

        config.tools.mcp_servers[normalized_name] = server
        save_config(config)

        return {
            "success": True,
            "server_name": normalized_name,
            "server": _mcp_server_to_dict(server),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update MCP server: {e}") from e


@router.delete("/mcp-servers/{server_name}")
async def delete_mcp_server(server_name: str):
    """Delete an MCP server definition."""
    normalized_name = server_name.strip()
    if not normalized_name:
        raise HTTPException(status_code=400, detail="Server name cannot be empty")

    try:
        config = load_config()
        if normalized_name not in config.tools.mcp_servers:
            raise HTTPException(status_code=404, detail=f"MCP server '{normalized_name}' not found")

        del config.tools.mcp_servers[normalized_name]
        save_config(config)

        return {
            "success": True,
            "server_name": normalized_name,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete MCP server: {e}") from e
