"""Config API endpoints."""

from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tokenmind.agent.tools.mcp import inspect_mcp_servers
from tokenmind.config.loader import load_config, save_config
from tokenmind.config.schema import AgentDefaults, Config, MCPServerConfig

router = APIRouter(prefix="/api/config", tags=["config"])

_PROVIDER_DEFAULT_MODELS: dict[str, str] = {
    "custom": "default",
    "anthropic": "claude-sonnet-4-5",
    "openai": "gpt-4o",
    "openrouter": "anthropic/claude-sonnet-4-5",
    "deepseek": "deepseek-chat",
    "zhipu": "glm-4",
    "dashscope": "qwen-max",
    "ollama": "llama3.2",
    "gemini": "gemini-2.0-flash",
    "moonshot": "kimi-k2.5",
    "minimax": "MiniMax-M2.7",
    "mimo": "",
    "siliconflow": "Qwen/Qwen2.5-7B-Instruct",
}


def _resolve_provider_default_model(
    config: Config,
    provider: str,
    current_model: str | None = None,
) -> str:
    provider_config = getattr(config.providers, provider, None)
    if provider_config and provider_config.default_model:
        return provider_config.default_model
    return _PROVIDER_DEFAULT_MODELS.get(provider) or current_model or config.agents.defaults.model


def _agent_defaults_are_initial(config: Config) -> bool:
    initial = AgentDefaults()
    defaults = config.agents.defaults
    return defaults.provider == initial.provider and defaults.model == initial.model


def _provider_has_connection(provider_config: object) -> bool:
    api_key = getattr(provider_config, "api_key", "")
    api_base = getattr(provider_config, "api_base", "")
    return bool((api_key or "").strip() or (api_base or "").strip())


class ProviderConfigUpdate(BaseModel):
    """Request model for updating a provider config."""

    api_key: str | None = None
    api_base: str | None = None
    extra_headers: dict[str, str] | None = None
    default_model: str | None = None


class CreativeCapabilityUpdate(BaseModel):
    """Request model for updating a creative capability config."""

    enabled: bool | None = None
    provider: str | None = None
    api_key: str | None = None
    api_base: str | None = None
    model: str | None = None
    extra_headers: dict[str, str] | None = None


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
    fallback_models: list[str] | None = None


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
    vlm_model: str | None = None
    vlm_api_key: str | None = None
    vlm_api_base: str | None = None
    vlm_timeout: int | None = None
    vlm_max_dim: int | None = None
    vlm_max_workers: int | None = None


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


class GatewayConfigUpdate(BaseModel):
    """Partial update for gateway configuration."""

    host: str | None = None
    port: int | None = None
    auth_secret: str | None = None


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

    enabled: bool | None = None
    notes: str | None = None
    icon: str | None = None
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
    creative: dict[str, dict[str, Any]]
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


def _creative_capability_to_dict(capability_config: object) -> dict[str, Any]:
    """Convert a creative capability config to dict with masked secrets."""
    return {
        "enabled": getattr(capability_config, "enabled", False),
        "provider": getattr(capability_config, "provider", ""),
        "api_key": _mask_api_key(getattr(capability_config, "api_key", "")),
        "api_base": getattr(capability_config, "api_base", None),
        "model": getattr(capability_config, "model", ""),
        "extra_headers": getattr(capability_config, "extra_headers", None),
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
        "enabled": server_config.enabled,
        "notes": server_config.notes,
        "icon": server_config.icon,
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

    creative_dict: dict[str, dict[str, Any]] = {}
    for capability_name in type(config.creative).model_fields:
        capability_config = getattr(config.creative, capability_name, None)
        if capability_config is not None:
            creative_dict[capability_name] = _creative_capability_to_dict(capability_config)

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
            "auth_secret": config.gateway.auth_secret,
        },
    }
    templates_dict = config.templates.model_dump()

    return ConfigResponse(
        providers=providers_dict,
        creative=creative_dict,
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

        if provider == config.agents.defaults.provider and "default_model" in update.model_fields_set:
            config.agents.defaults.model = _resolve_provider_default_model(
                config,
                provider,
                current_model=config.agents.defaults.model,
            )
        elif _agent_defaults_are_initial(config) and _provider_has_connection(provider_config):
            config.agents.defaults.provider = provider
            config.agents.defaults.model = _resolve_provider_default_model(
                config,
                provider,
                current_model=config.agents.defaults.model,
            )

        save_config(config)

        return {
            "success": True,
            "provider": provider,
            "config": _provider_config_to_dict(provider_config),
            "defaults": {
                "model": config.agents.defaults.model,
                "provider": config.agents.defaults.provider,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update provider: {e}") from e


@router.put("/creative/{capability}")
async def update_creative_config(capability: str, update: CreativeCapabilityUpdate):
    """Update a specific creative capability configuration."""
    try:
        config = load_config()

        if not hasattr(config.creative, capability):
            raise HTTPException(status_code=404, detail=f"Creative capability '{capability}' not found")

        capability_config = getattr(config.creative, capability)

        if "enabled" in update.model_fields_set:
            capability_config.enabled = bool(update.enabled)
        if "provider" in update.model_fields_set:
            capability_config.provider = update.provider or ""
        if "api_key" in update.model_fields_set:
            capability_config.api_key = update.api_key or ""
        if "api_base" in update.model_fields_set:
            capability_config.api_base = update.api_base
        if "model" in update.model_fields_set:
            capability_config.model = update.model or ""
        if "extra_headers" in update.model_fields_set:
            capability_config.extra_headers = update.extra_headers or None

        save_config(config)

        return {
            "success": True,
            "capability": capability,
            "config": _creative_capability_to_dict(capability_config),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update creative capability: {e}") from e


@router.put("/defaults")
async def update_defaults(update: DefaultsUpdate):
    """Update the default agent configuration."""
    try:
        config = load_config()

        if update.provider is not None:
            config.agents.defaults.provider = update.provider
        if update.model is not None:
            config.agents.defaults.model = update.model
        elif update.provider is not None:
            config.agents.defaults.model = _resolve_provider_default_model(
                config,
                update.provider,
                current_model=config.agents.defaults.model,
            )

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
        if "provider" in update.model_fields_set:
            defaults.provider = update.provider
            if "model" not in update.model_fields_set and update.provider:
                defaults.model = _resolve_provider_default_model(
                    config,
                    update.provider,
                    current_model=defaults.model,
                )
        if "model" in update.model_fields_set:
            defaults.model = update.model
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
        if "fallback_models" in update.model_fields_set:
            # Strip blank entries and dedupe while preserving order so users
            # can paste a comma-/newline-separated list without worrying
            # about extra whitespace.
            cleaned: list[str] = []
            seen: set[str] = set()
            for item in update.fallback_models or []:
                token = (item or "").strip()
                if token and token not in seen:
                    cleaned.append(token)
                    seen.add(token)
            defaults.fallback_models = cleaned

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
            if "vlm_model" in update.knowledge.model_fields_set:
                knowledge.vlm_model = update.knowledge.vlm_model or ""
            if "vlm_api_key" in update.knowledge.model_fields_set:
                knowledge.vlm_api_key = update.knowledge.vlm_api_key or ""
            if "vlm_api_base" in update.knowledge.model_fields_set:
                knowledge.vlm_api_base = update.knowledge.vlm_api_base or None
            if "vlm_timeout" in update.knowledge.model_fields_set:
                knowledge.vlm_timeout = update.knowledge.vlm_timeout
            if "vlm_max_dim" in update.knowledge.model_fields_set:
                knowledge.vlm_max_dim = update.knowledge.vlm_max_dim
            if "vlm_max_workers" in update.knowledge.model_fields_set:
                knowledge.vlm_max_workers = update.knowledge.vlm_max_workers

        save_config(config)

        return {
            "success": True,
            "tools": _build_config_response().tools,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update tools config: {e}") from e


def _refresh_app_auth_secret(new_secret: str) -> None:
    """Mirror gateway.auth_secret onto the running FastAPI app.state so the
    LAN auth middleware picks up rotations immediately instead of needing a
    restart."""
    try:
        from tokenmind.server.dependencies import get_app

        app = get_app()
        if app is not None:
            app.state.auth_secret = new_secret or ""
    except Exception:  # pragma: no cover — best effort
        pass


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
            if "auth_secret" in update.gateway.model_fields_set:
                new_secret = (update.gateway.auth_secret or "").strip()
                config.gateway.auth_secret = new_secret
                _refresh_app_auth_secret(new_secret)

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

        if "enabled" in update.model_fields_set:
            server.enabled = bool(update.enabled)
        if "notes" in update.model_fields_set:
            server.notes = update.notes or ""
        if "icon" in update.model_fields_set:
            server.icon = update.icon or ""
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


# ──────────────────────────────────────────────────────────────────────────
# External chat channels (Chinese-app focused: Feishu / DingTalk / WeCom / QQ / Mochat)
# ──────────────────────────────────────────────────────────────────────────


_CHANNEL_REGISTRY: dict[str, dict[str, Any]] = {
    "feishu": {
        "label": "飞书",
        "description": "通过飞书开放平台 WebSocket 长连接接入。",
        "fields": ["app_id", "app_secret", "encrypt_key", "verification_token", "allow_from"],
        "required": ["app_id", "app_secret", "allow_from"],
    },
    "dingtalk": {
        "label": "钉钉",
        "description": "通过钉钉 Stream 模式接入。",
        "fields": ["client_id", "client_secret", "allow_from"],
        "required": ["client_id", "client_secret", "allow_from"],
    },
    "wecom": {
        "label": "企业微信",
        "description": "企业微信 AI 智能机器人。",
        "fields": ["bot_id", "secret", "allow_from", "welcome_message"],
        "required": ["bot_id", "secret", "allow_from"],
    },
    "qq": {
        "label": "QQ",
        "description": "QQ 官方机器人（需在 QQ 开放平台申请）。",
        "fields": ["app_id", "secret", "allow_from", "msg_format"],
        "required": ["app_id", "secret", "allow_from"],
    },
    "mochat": {
        "label": "Mochat（个微）",
        "description": "通过 Mochat 接入个人微信。",
        "fields": ["base_url", "claw_token", "agent_user_id", "allow_from"],
        "required": ["base_url", "claw_token", "agent_user_id", "allow_from"],
    },
}


def _missing_required_fields(channel_name: str, config: dict[str, Any]) -> list[str]:
    required = _CHANNEL_REGISTRY[channel_name].get("required", [])
    missing: list[str] = []
    for field in required:
        value = config.get(field)
        if (
            value is None
            or (isinstance(value, str) and not value.strip())
            or (isinstance(value, list) and not value)
        ):
            missing.append(field)
    return missing


def _camel_to_snake(value: str) -> str:
    value = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value).lower()


def _is_empty_config_value(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _normalize_channel_config(config: dict[str, Any]) -> dict[str, Any]:
    """Use snake_case keys for channel configs and collapse alias duplicates."""
    normalized: dict[str, Any] = {}
    for raw_key, value in config.items():
        key = _camel_to_snake(str(raw_key))
        if key in normalized:
            existing = normalized[key]
            if _is_empty_config_value(existing) and not _is_empty_config_value(value):
                normalized[key] = value
            elif not _is_empty_config_value(value) or _is_empty_config_value(existing):
                normalized[key] = value
            continue
        normalized[key] = value
    return normalized


def _get_channel_section(config: Config, name: str) -> dict[str, Any]:
    """Read a channel's stored config as a plain dict, defaulting to disabled."""
    section = getattr(config.channels, name, None)
    if isinstance(section, dict):
        return _normalize_channel_config(dict(section))
    if section is None:
        return {"enabled": False}
    raw = section.model_dump(by_alias=False) if hasattr(section, "model_dump") else dict(section)
    return _normalize_channel_config(raw)


@router.get("/channels")
async def list_channels():
    """Return the catalog of supported channels with their current configuration."""
    try:
        config = load_config()
        channels = []
        for name, meta in _CHANNEL_REGISTRY.items():
            stored = _get_channel_section(config, name)
            channels.append(
                {
                    "name": name,
                    "label": meta["label"],
                    "description": meta["description"],
                    "fields": meta["fields"],
                    "required": meta.get("required", []),
                    "enabled": bool(stored.get("enabled", False)),
                    "config": stored,
                }
            )
        return {"channels": channels}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load channels: {e}") from e


class ChannelConfigUpdate(BaseModel):
    """Free-form channel config update; backend validates per-channel schema on save."""

    model_config = {"extra": "allow"}

    enabled: bool | None = None


@router.put("/channels/{channel_name}")
async def update_channel(channel_name: str, payload: ChannelConfigUpdate):
    """Create or update an external channel configuration."""
    if channel_name not in _CHANNEL_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown channel '{channel_name}'")

    try:
        config = load_config()
        current = _get_channel_section(config, channel_name)
        update_dict = _normalize_channel_config(payload.model_dump(exclude_unset=True))
        merged = _normalize_channel_config({**current, **update_dict})
        # Default enabled to False if not set, so saved configs are deterministic.
        merged.setdefault("enabled", False)

        # Block enabling when required fields are missing/empty.
        if merged.get("enabled"):
            missing = _missing_required_fields(channel_name, merged)
            if missing:
                label = _CHANNEL_REGISTRY[channel_name]["label"]
                raise HTTPException(
                    status_code=400,
                    detail=f"无法启用 {label}：缺少必填项 {', '.join(missing)}",
                )

        setattr(config.channels, channel_name, merged)
        save_config(config)

        from tokenmind.server.dependencies import get_channel_manager

        channel_manager = get_channel_manager()
        if channel_manager is not None:
            await channel_manager.refresh_channel(channel_name, merged)

        return {"success": True, "name": channel_name, "config": merged}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update channel: {e}") from e
