"""MCP client: connects to MCP servers and wraps their tools as native sun_agent tools."""

import asyncio
from contextlib import AsyncExitStack
from typing import Any

import httpx
from loguru import logger

from sun_agent.agent.tools.base import Tool
from sun_agent.agent.tools.registry import ToolRegistry


def _resolve_transport_type(cfg: Any) -> str:
    """Resolve MCP transport type from config."""
    transport_type = getattr(cfg, "type", None)
    if transport_type:
        return transport_type

    if getattr(cfg, "command", ""):
        return "stdio"

    if getattr(cfg, "url", ""):
        return "sse" if str(cfg.url).rstrip("/").endswith("/sse") else "streamableHttp"

    raise ValueError("no command or url configured")


async def _open_mcp_transport(cfg: Any, transport_type: str, stack: AsyncExitStack):
    """Open an MCP transport and return the reader/writer pair."""
    from mcp import StdioServerParameters
    from mcp.client.sse import sse_client
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamable_http_client

    if transport_type == "stdio":
        params = StdioServerParameters(
            command=cfg.command,
            args=cfg.args,
            env=cfg.env or None,
        )
        return await stack.enter_async_context(stdio_client(params))

    if transport_type == "sse":

        def httpx_client_factory(
            headers: dict[str, str] | None = None,
            timeout: httpx.Timeout | None = None,
            auth: httpx.Auth | None = None,
        ) -> httpx.AsyncClient:
            merged_headers = {**(cfg.headers or {}), **(headers or {})}
            return httpx.AsyncClient(
                headers=merged_headers or None,
                follow_redirects=True,
                timeout=timeout,
                auth=auth,
            )

        return await stack.enter_async_context(
            sse_client(cfg.url, httpx_client_factory=httpx_client_factory)
        )

    if transport_type == "streamableHttp":
        # Always provide an explicit httpx client so MCP HTTP transport does not
        # inherit httpx's default 5s timeout and preempt the higher-level tool timeout.
        http_client = await stack.enter_async_context(
            httpx.AsyncClient(
                headers=cfg.headers or None,
                follow_redirects=True,
                timeout=None,
            )
        )
        read, write, _ = await stack.enter_async_context(
            streamable_http_client(cfg.url, http_client=http_client)
        )
        return read, write

    raise ValueError(f"unknown transport type '{transport_type}'")


async def inspect_mcp_servers(mcp_servers: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Inspect configured MCP servers and return their discovered tool catalogs."""
    from mcp import ClientSession

    discovered: dict[str, dict[str, Any]] = {}

    for server_name, cfg in mcp_servers.items():
        result: dict[str, Any] = {
            "status": "error",
            "transport_type": None,
            "tool_count": 0,
            "enabled_count": 0,
            "tools": [],
            "error": None,
        }

        try:
            transport_type = _resolve_transport_type(cfg)
            result["transport_type"] = transport_type

            async with AsyncExitStack() as stack:
                read, write = await _open_mcp_transport(cfg, transport_type, stack)
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                tools = await session.list_tools()

            enabled_tools = set(getattr(cfg, "enabled_tools", []) or [])
            allow_all_tools = "*" in enabled_tools
            discovered_tools = []
            for tool_def in tools.tools:
                wrapped_name = f"mcp_{server_name}_{tool_def.name}"
                enabled = (
                    allow_all_tools
                    or tool_def.name in enabled_tools
                    or wrapped_name in enabled_tools
                )
                discovered_tools.append(
                    {
                        "name": tool_def.name,
                        "wrapped_name": wrapped_name,
                        "description": tool_def.description or "",
                        "enabled": enabled,
                    }
                )

            discovered_tools.sort(key=lambda item: (not item["enabled"], item["name"]))
            result.update(
                {
                    "status": "connected",
                    "tool_count": len(discovered_tools),
                    "enabled_count": sum(1 for tool in discovered_tools if tool["enabled"]),
                    "tools": discovered_tools,
                }
            )
        except Exception as exc:
            logger.error("MCP server '{}': failed to inspect tools: {}", server_name, exc)
            result["error"] = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__

        discovered[server_name] = result

    return discovered


class MCPToolWrapper(Tool):
    """Wraps a single MCP server tool as a sun_agent Tool."""

    def __init__(self, session, server_name: str, tool_def, tool_timeout: int = 30):
        self._session = session
        self._original_name = tool_def.name
        self._name = f"mcp_{server_name}_{tool_def.name}"
        self._description = tool_def.description or tool_def.name
        self._parameters = tool_def.inputSchema or {"type": "object", "properties": {}}
        self._tool_timeout = tool_timeout

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def execute(self, **kwargs: Any) -> str:
        from mcp import types

        try:
            result = await asyncio.wait_for(
                self._session.call_tool(self._original_name, arguments=kwargs),
                timeout=self._tool_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("MCP tool '{}' timed out after {}s", self._name, self._tool_timeout)
            return f"(MCP tool call timed out after {self._tool_timeout}s)"
        except asyncio.CancelledError:
            # MCP SDK's anyio cancel scopes can leak CancelledError on timeout/failure.
            # Re-raise only if our task was externally cancelled (e.g. /stop).
            task = asyncio.current_task()
            if task is not None and task.cancelling() > 0:
                raise
            logger.warning("MCP tool '{}' was cancelled by server/SDK", self._name)
            return "(MCP tool call was cancelled)"
        except Exception as exc:
            logger.exception(
                "MCP tool '{}' failed: {}: {}",
                self._name,
                type(exc).__name__,
                exc,
            )
            return f"(MCP tool call failed: {type(exc).__name__})"

        parts = []
        for block in result.content:
            if isinstance(block, types.TextContent):
                parts.append(block.text)
            else:
                parts.append(str(block))
        return "\n".join(parts) or "(no output)"


async def connect_mcp_servers(
    mcp_servers: dict, registry: ToolRegistry, stack: AsyncExitStack
) -> None:
    """Connect to configured MCP servers and register their tools."""
    from mcp import ClientSession

    for name, cfg in mcp_servers.items():
        try:
            try:
                transport_type = _resolve_transport_type(cfg)
            except ValueError:
                logger.warning("MCP server '{}': no command or url configured, skipping", name)
                continue

            read, write = await _open_mcp_transport(cfg, transport_type, stack)

            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()

            tools = await session.list_tools()
            enabled_tools = set(cfg.enabled_tools)
            allow_all_tools = "*" in enabled_tools
            registered_count = 0
            matched_enabled_tools: set[str] = set()
            available_raw_names = [tool_def.name for tool_def in tools.tools]
            available_wrapped_names = [f"mcp_{name}_{tool_def.name}" for tool_def in tools.tools]
            for tool_def in tools.tools:
                wrapped_name = f"mcp_{name}_{tool_def.name}"
                if (
                    not allow_all_tools
                    and tool_def.name not in enabled_tools
                    and wrapped_name not in enabled_tools
                ):
                    logger.debug(
                        "MCP: skipping tool '{}' from server '{}' (not in enabledTools)",
                        wrapped_name,
                        name,
                    )
                    continue
                wrapper = MCPToolWrapper(session, name, tool_def, tool_timeout=cfg.tool_timeout)
                registry.register(wrapper)
                logger.debug("MCP: registered tool '{}' from server '{}'", wrapper.name, name)
                registered_count += 1
                if enabled_tools:
                    if tool_def.name in enabled_tools:
                        matched_enabled_tools.add(tool_def.name)
                    if wrapped_name in enabled_tools:
                        matched_enabled_tools.add(wrapped_name)

            if enabled_tools and not allow_all_tools:
                unmatched_enabled_tools = sorted(enabled_tools - matched_enabled_tools)
                if unmatched_enabled_tools:
                    logger.warning(
                        "MCP server '{}': enabledTools entries not found: {}. Available raw names: {}. "
                        "Available wrapped names: {}",
                        name,
                        ", ".join(unmatched_enabled_tools),
                        ", ".join(available_raw_names) or "(none)",
                        ", ".join(available_wrapped_names) or "(none)",
                    )

            logger.info("MCP server '{}': connected, {} tools registered", name, registered_count)
        except Exception as e:
            logger.error("MCP server '{}': failed to connect: {}", name, e)
