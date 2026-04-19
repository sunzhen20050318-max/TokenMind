"""Tests for config API route helpers."""

from __future__ import annotations

import pytest


@pytest.fixture
def temp_config_path(tmp_path):
    """Point config loader at a temporary config file for the test."""
    from sun_agent.config.loader import get_config_path, set_config_path

    previous = get_config_path()
    path = tmp_path / "config.json"
    set_config_path(path)
    try:
        yield path
    finally:
        set_config_path(previous)


@pytest.mark.asyncio
async def test_get_config_returns_extended_sections(temp_config_path):
    """GET config should expose agent, tools, runtime, and MCP data."""
    from sun_agent.config.loader import save_config
    from sun_agent.config.schema import Config, MCPServerConfig
    from sun_agent.server.routes.config import get_config

    config = Config()
    config.providers.openai.api_key = "sk-test-12345678"
    config.providers.openai.default_model = "gpt-4.1"
    config.tools.web.search.api_key = "search-secret-9876"
    config.templates.response = "{{ content }}"
    config.tools.mcp_servers["docs"] = MCPServerConfig(
        type="stdio",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem"],
        enabled_tools=["*"],
    )
    save_config(config, temp_config_path)

    response = await get_config()

    assert response.agent["context_window_tokens"] == 65_536
    assert response.providers["openai"]["api_key"] == "****5678"
    assert response.providers["openai"]["default_model"] == "gpt-4.1"
    assert response.tools["web"]["search"]["api_key"] == "****9876"
    assert response.tools["exec"]["confirm_high_risk"] is True
    assert response.tools["exec"]["approval_timeout_s"] == 300
    assert response.tools["uploads"]["max_file_mb"] == 50
    assert response.tools["knowledge"]["vector_backend"] == "qdrant"
    assert response.tools["audit_enabled"] is True
    assert response.tools["mcp_servers"]["docs"]["command"] == "npx"
    assert response.runtime["gateway"]["heartbeat"]["enabled"] is True
    assert response.templates["response"] == "{{ content }}"


@pytest.mark.asyncio
async def test_get_mcp_tools_returns_discovered_catalog(temp_config_path, monkeypatch):
    """GET MCP tools should expose live discovered tool metadata for each server."""
    from sun_agent.config.loader import save_config
    from sun_agent.config.schema import Config, MCPServerConfig
    from sun_agent.server.routes import config as config_routes

    config = Config()
    config.tools.mcp_servers["minimax"] = MCPServerConfig(
        type="stdio",
        command="python",
        args=["-c", "pass"],
        enabled_tools=["*"],
    )
    save_config(config, temp_config_path)

    async def fake_inspect_mcp_servers(mcp_servers):
        assert "minimax" in mcp_servers
        return {
            "minimax": {
                "status": "connected",
                "transport_type": "stdio",
                "tool_count": 2,
                "enabled_count": 2,
                "tools": [
                    {
                        "name": "web_search",
                        "wrapped_name": "mcp_minimax_web_search",
                        "description": "Search the web",
                        "enabled": True,
                    },
                    {
                        "name": "understand_image",
                        "wrapped_name": "mcp_minimax_understand_image",
                        "description": "Inspect an image",
                        "enabled": True,
                    },
                ],
                "error": None,
            }
        }

    monkeypatch.setattr(config_routes, "inspect_mcp_servers", fake_inspect_mcp_servers)

    response = await config_routes.get_mcp_tools()

    assert response["servers"]["minimax"]["tool_count"] == 2
    assert response["servers"]["minimax"]["tools"][0]["wrapped_name"] == "mcp_minimax_web_search"
    assert response["servers"]["minimax"]["status"] == "connected"


@pytest.mark.asyncio
async def test_update_config_sections_and_mcp_servers(temp_config_path):
    """Route helpers should persist provider, agent, tools, runtime, and MCP updates."""
    from sun_agent.config.loader import load_config
    from sun_agent.server.routes.config import (
        AgentConfigUpdate,
        ChannelsConfigUpdate,
        ExecToolConfigUpdate,
        GatewayConfigUpdate,
        HeartbeatConfigUpdate,
        KnowledgeConfigUpdate,
        MCPServerConfigUpdate,
        ProviderConfigUpdate,
        RuntimeConfigUpdate,
        TemplatesConfigUpdate,
        ToolsConfigUpdate,
        UploadsConfigUpdate,
        WebSearchConfigUpdate,
        WebToolsConfigUpdate,
        delete_mcp_server,
        update_agent_config,
        update_provider_config,
        update_runtime_config,
        update_templates_config,
        update_tools_config,
        upsert_mcp_server,
    )

    await update_provider_config(
        "openai",
        ProviderConfigUpdate(
            api_key="sk-updated-1234",
            api_base="https://api.openai.example",
            default_model="gpt-4.1-mini",
            extra_headers={"x-app": "sun"},
        ),
    )
    await update_agent_config(
        AgentConfigUpdate(
            workspace="~/workspace-test",
            model="openai/gpt-4.1-mini",
            provider="openai",
            max_tokens=4096,
            context_window_tokens=32768,
            temperature=0.4,
            max_tool_iterations=12,
            reasoning_effort="medium",
        )
    )
    await update_tools_config(
        ToolsConfigUpdate(
            restrict_to_workspace=True,
            web=WebToolsConfigUpdate(
                proxy="http://127.0.0.1:7890",
                search=WebSearchConfigUpdate(
                    provider="tavily",
                    api_key="tavily-secret",
                    base_url="https://search.example",
                    max_results=8,
                ),
            ),
            exec=ExecToolConfigUpdate(
                timeout=90,
                path_append="C:\\tools",
                confirm_high_risk=False,
                approval_timeout_s=180,
            ),
            uploads=UploadsConfigUpdate(
                max_file_mb=80,
                max_total_mb=2048,
                retention_days=21,
                cleanup_interval_hours=6,
            ),
            knowledge=KnowledgeConfigUpdate(
                vector_backend="sqlite",
                chunk_size=1024,
                chunk_overlap=160,
                top_k=8,
                embedding_model="text-embedding-3-small",
                embedding_api_key="embed-secret",
                embedding_api_base="https://embed.example/v1",
            ),
            audit_enabled=False,
        )
    )
    await update_runtime_config(
        RuntimeConfigUpdate(
            channels=ChannelsConfigUpdate(send_progress=False, send_tool_hints=True),
            gateway=GatewayConfigUpdate(
                host="127.0.0.1",
                port=8080,
                heartbeat=HeartbeatConfigUpdate(enabled=False, interval_s=120),
            ),
        )
    )
    await update_templates_config(
        TemplatesConfigUpdate(
            response="{{ content }}",
            memory_system="You are {{ role_name }}.",
            memory_prompt="COUNT={{ message_count }}",
        )
    )
    await upsert_mcp_server(
        "filesystem",
        MCPServerConfigUpdate(
            type="stdio",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem"],
            env={"ROOT": "D:/project"},
            headers={},
            tool_timeout=45,
            enabled_tools=["read_file", "list_dir"],
        ),
    )

    config = load_config(temp_config_path)
    assert config.providers.openai.api_key == "sk-updated-1234"
    assert config.providers.openai.default_model == "gpt-4.1-mini"
    assert config.agents.defaults.workspace == "~/workspace-test"
    assert config.agents.defaults.reasoning_effort == "medium"
    assert config.tools.restrict_to_workspace is True
    assert config.tools.web.search.provider == "tavily"
    assert config.tools.exec.timeout == 90
    assert config.tools.exec.confirm_high_risk is False
    assert config.tools.exec.approval_timeout_s == 180
    assert config.tools.uploads.max_file_mb == 80
    assert config.tools.uploads.max_total_mb == 2048
    assert config.tools.uploads.retention_days == 21
    assert config.tools.uploads.cleanup_interval_hours == 6
    assert config.tools.knowledge.chunk_size == 1024
    assert config.tools.knowledge.chunk_overlap == 160
    assert config.tools.knowledge.top_k == 8
    assert config.tools.knowledge.embedding_model == "text-embedding-3-small"
    assert config.tools.knowledge.embedding_api_base == "https://embed.example/v1"
    assert config.tools.audit_enabled is False
    assert config.channels.send_progress is False
    assert config.gateway.heartbeat.interval_s == 120
    assert config.templates.response == "{{ content }}"
    assert config.templates.memory_system == "You are {{ role_name }}."
    assert config.templates.memory_prompt == "COUNT={{ message_count }}"
    assert config.tools.mcp_servers["filesystem"].env["ROOT"] == "D:/project"

    await delete_mcp_server("filesystem")

    config = load_config(temp_config_path)
    assert "filesystem" not in config.tools.mcp_servers
