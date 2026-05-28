"""Configuration schema using Pydantic."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from pydantic_settings import BaseSettings


class Base(BaseModel):
    """Base model that accepts both camelCase and snake_case keys."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

class ChannelsConfig(Base):
    """Configuration for chat channels.

    Built-in and plugin channel configs are stored as extra fields (dicts).
    Each channel parses its own config in __init__.
    """

    model_config = ConfigDict(extra="allow")

    send_progress: bool = True  # stream agent's text progress to the channel
    send_tool_hints: bool = False  # stream tool-call hints (e.g. read_file("…"))


class AgentDefaults(Base):
    """Default agent configuration."""

    workspace: str = "~/.tokenmind/workspace"
    model: str = "anthropic/claude-opus-4-5"
    provider: str = (
        "auto"  # Provider name (e.g. "anthropic", "openrouter") or "auto" for auto-detection
    )
    max_tokens: int = 16384
    context_window_tokens: int = 65_536
    temperature: float = 0.1
    max_tool_iterations: int = 40
    reasoning_effort: str | None = None  # low / medium / high - enables LLM thinking mode
    # Ordered list of fully-qualified model strings (e.g. "deepseek/deepseek-chat",
    # "anthropic/claude-haiku-4-5") to try in order when the primary `model`
    # call returns finish_reason="error". Each entry routes to its own
    # provider via the existing model-prefix detection. Empty list (default)
    # disables failover entirely. National providers (Moonshot, MiniMax,
    # DashScope etc.) frequently rate-limit during peak hours — listing one
    # or two cheap alternatives means a single timeout doesn't break the
    # conversation.
    fallback_models: list[str] = Field(default_factory=list)


class AgentsConfig(Base):
    """Agent configuration."""

    defaults: AgentDefaults = Field(default_factory=AgentDefaults)


class ProviderConfig(Base):
    """LLM provider configuration."""

    api_key: str = ""
    api_base: str | None = None
    extra_headers: dict[str, str] | None = None  # Custom HTTP headers for compatible endpoints
    default_model: str | None = None


class ProvidersConfig(Base):
    """Configuration for LLM providers."""

    custom: ProviderConfig = Field(default_factory=ProviderConfig)  # Any OpenAI-compatible endpoint
    anthropic: ProviderConfig = Field(default_factory=ProviderConfig)
    openai: ProviderConfig = Field(default_factory=ProviderConfig)
    openrouter: ProviderConfig = Field(default_factory=ProviderConfig)
    deepseek: ProviderConfig = Field(default_factory=ProviderConfig)
    zhipu: ProviderConfig = Field(default_factory=ProviderConfig)
    dashscope: ProviderConfig = Field(default_factory=ProviderConfig)
    ollama: ProviderConfig = Field(default_factory=ProviderConfig)  # Ollama local models
    gemini: ProviderConfig = Field(default_factory=ProviderConfig)
    moonshot: ProviderConfig = Field(default_factory=ProviderConfig)
    minimax: ProviderConfig = Field(default_factory=ProviderConfig)
    mimo: ProviderConfig = Field(default_factory=ProviderConfig)  # Xiaomi MiMo
    siliconflow: ProviderConfig = Field(default_factory=ProviderConfig)  # SiliconFlow


class CreativeCapabilityConfig(Base):
    """Configuration for a creative capability provider."""

    enabled: bool = False
    provider: str = ""
    api_key: str = ""
    api_base: str | None = None
    model: str = ""
    extra_headers: dict[str, str] | None = None


class CreativeConfig(Base):
    """Configuration for creative capabilities."""

    image: CreativeCapabilityConfig = Field(default_factory=CreativeCapabilityConfig)
    music: CreativeCapabilityConfig = Field(default_factory=CreativeCapabilityConfig)
    music_cover: CreativeCapabilityConfig = Field(default_factory=CreativeCapabilityConfig)
    voice_clone: CreativeCapabilityConfig = Field(default_factory=CreativeCapabilityConfig)
    tts: CreativeCapabilityConfig = Field(default_factory=CreativeCapabilityConfig)
    voice_design: CreativeCapabilityConfig = Field(default_factory=CreativeCapabilityConfig)
    video: CreativeCapabilityConfig = Field(default_factory=CreativeCapabilityConfig)


class GatewayConfig(Base):
    """Gateway/server configuration."""

    host: str = "0.0.0.0"
    port: int = 18888
    # Shared secret required from any non-localhost client. Auto-generated on
    # first startup when host is LAN-exposed (0.0.0.0 / ::) and this is
    # empty. Local (127.0.0.1) requests are always allowed without it, so
    # the user never needs to enter it when accessing TokenMind on the same
    # machine the server runs on.
    auth_secret: str = ""


class WebSearchConfig(Base):
    """Web search tool configuration."""

    provider: str = "brave"  # brave, tavily, duckduckgo, searxng, jina
    api_key: str = ""
    base_url: str = ""  # SearXNG base URL
    max_results: int = 5


class WebToolsConfig(Base):
    """Web tools configuration."""

    proxy: str | None = (
        None  # HTTP/SOCKS5 proxy URL, e.g. "http://127.0.0.1:7890" or "socks5://127.0.0.1:1080"
    )
    search: WebSearchConfig = Field(default_factory=WebSearchConfig)


class ExecToolConfig(Base):
    """Shell exec tool configuration."""

    timeout: int = 60
    path_append: str = ""
    confirm_high_risk: bool = True
    approval_timeout_s: int = 300


class UploadsConfig(Base):
    """Upload storage policy configuration."""

    max_file_mb: int = 50
    max_total_mb: int = 1024
    retention_days: int = 30
    cleanup_interval_hours: int = 12


class KnowledgeConfig(Base):
    """Knowledge base ingestion and retrieval configuration."""

    vector_backend: str = "qdrant"
    chunk_size: int = 900
    chunk_overlap: int = 120
    top_k: int = 6
    embedding_model: str = ""
    embedding_api_key: str = ""
    embedding_api_base: str | None = None
    rerank_model: str = ""
    rerank_api_key: str = ""
    rerank_api_base: str | None = None
    rerank_top_n: int = 12
    # Optional vision-language model for richer document parsing. When the
    # model is configured, complex PDF pages and embedded Office images get
    # captioned by the VLM during ingestion; otherwise the knowledge base
    # falls back to plain text extraction.
    vlm_model: str = ""
    vlm_api_key: str = ""
    vlm_api_base: str | None = None
    vlm_timeout: int = 30
    vlm_max_dim: int = 1280
    # Concurrent VLM HTTP calls per document. Larger values trade higher
    # peak API spend for faster ingestion on image-heavy files.
    vlm_max_workers: int = 8


class TemplatesConfig(Base):
    """Optional Jinja2 templates for response and memory flows."""

    response: str | None = None
    memory_system: str | None = None
    memory_prompt: str | None = None


class MemoryConfig(Base):
    """Long-term memory summary + purification settings.

    MEMORY.md is the append-only source of truth; it is NOT injected into the
    system prompt directly. Instead the consolidation pass also emits a
    compressed summary (capped at ``summary_max_tokens``) and that summary is
    what every turn sees. MEMORY.md itself is periodically purified back under
    ``purify_max_tokens`` so it never grows without bound.
    """

    summary_enabled: bool = True
    summary_max_tokens: int = 4000  # cap for the injected long-term summary
    purify_max_tokens: int = 10000  # MEMORY.md is compressed back under this
    purify_interval_days: int = 7  # min days between MEMORY.md purifications (<=0 disables)


class MCPServerConfig(Base):
    """MCP server connection configuration (stdio or HTTP)."""

    enabled: bool = True  # Master switch — disabled servers are skipped at runtime
    notes: str = ""  # Free-form notes (UI-only metadata)
    icon: str = ""  # Optional icon URL (UI-only metadata)
    type: Literal["stdio", "sse", "streamableHttp"] | None = None  # auto-detected if omitted
    command: str = ""  # Stdio: command to run (e.g. "npx")
    args: list[str] = Field(default_factory=list)  # Stdio: command arguments
    env: dict[str, str] = Field(default_factory=dict)  # Stdio: extra env vars
    url: str = ""  # HTTP/SSE: endpoint URL
    headers: dict[str, str] = Field(default_factory=dict)  # HTTP/SSE: custom headers
    tool_timeout: int = 30  # seconds before a tool call is cancelled
    enabled_tools: list[str] = Field(default_factory=lambda: ["*"])  # Only register these tools; accepts raw MCP names or wrapped mcp_<server>_<tool> names; ["*"] = all tools; [] = no tools

class ToolsConfig(Base):
    """Tools configuration."""

    web: WebToolsConfig = Field(default_factory=WebToolsConfig)
    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)
    uploads: UploadsConfig = Field(default_factory=UploadsConfig)
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)
    audit_enabled: bool = True
    restrict_to_workspace: bool = False  # If true, restrict all tool access to workspace directory
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)


class SkillsConfig(Base):
    """Skills configuration.

    Skills are opt-out: by default every installed skill is enabled. The
    ``disabled`` list captures skills the user explicitly turned off so new
    built-ins automatically become available.
    """

    disabled: list[str] = Field(default_factory=list)


class Config(BaseSettings):
    """Root configuration for tokenmind."""

    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    creative: CreativeConfig = Field(default_factory=CreativeConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    templates: TemplatesConfig = Field(default_factory=TemplatesConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)

    @property
    def workspace_path(self) -> Path:
        """Get expanded workspace path."""
        return Path(self.agents.defaults.workspace).expanduser()

    def _match_provider(
        self, model: str | None = None
    ) -> tuple["ProviderConfig | None", str | None]:
        """Match provider config and its registry name. Returns (config, spec_name)."""
        from tokenmind.providers.registry import PROVIDERS

        forced = self.agents.defaults.provider
        if forced != "auto":
            p = getattr(self.providers, forced, None)
            if p:
                return p, forced

        model_lower = (model or self.agents.defaults.model).lower()
        model_normalized = model_lower.replace("-", "_")
        model_prefix = model_lower.split("/", 1)[0] if "/" in model_lower else ""
        normalized_prefix = model_prefix.replace("-", "_")

        def _kw_matches(kw: str) -> bool:
            kw = kw.lower()
            return kw in model_lower or kw.replace("-", "_") in model_normalized

        # Explicit provider prefix wins over fuzzy keyword matching.
        for spec in PROVIDERS:
            p = getattr(self.providers, spec.name, None)
            if p and model_prefix and normalized_prefix == spec.name:
                if spec.is_oauth or spec.is_local or p.api_key:
                    return p, spec.name

        # Match by keyword (order follows PROVIDERS registry)
        for spec in PROVIDERS:
            p = getattr(self.providers, spec.name, None)
            if p and any(_kw_matches(kw) for kw in spec.keywords):
                if spec.is_oauth or spec.is_local or p.api_key:
                    return p, spec.name

        # Fallback: configured local providers can route models without
        # provider-specific keywords (for example plain "llama3.2" on Ollama).
        # Prefer providers whose detect_by_base_keyword matches the configured api_base
        # (e.g. Ollama's "11434" in "http://localhost:11434") over plain registry order.
        local_fallback: tuple[ProviderConfig, str] | None = None
        for spec in PROVIDERS:
            if not spec.is_local:
                continue
            p = getattr(self.providers, spec.name, None)
            if not (p and p.api_base):
                continue
            if spec.detect_by_base_keyword and spec.detect_by_base_keyword in p.api_base:
                return p, spec.name
            if local_fallback is None:
                local_fallback = (p, spec.name)
        if local_fallback:
            return local_fallback

        # Fallback: gateways first, then others (follows registry order)
        # OAuth providers are NOT valid fallbacks — they require explicit model selection
        for spec in PROVIDERS:
            if spec.is_oauth:
                continue
            p = getattr(self.providers, spec.name, None)
            if p and p.api_key:
                return p, spec.name
        return None, None

    def get_provider(self, model: str | None = None) -> ProviderConfig | None:
        """Get matched provider config (api_key, api_base, extra_headers). Falls back to first available."""
        p, _ = self._match_provider(model)
        return p

    def get_provider_name(self, model: str | None = None) -> str | None:
        """Get the registry name of the matched provider (e.g. "deepseek", "openrouter")."""
        _, name = self._match_provider(model)
        return name

    def get_api_key(self, model: str | None = None) -> str | None:
        """Get API key for the given model. Falls back to first available key."""
        p = self.get_provider(model)
        return p.api_key if p else None

    def get_api_base(self, model: str | None = None) -> str | None:
        """Get API base URL for the given model, falling back to registry defaults."""
        from tokenmind.providers.registry import find_by_name

        p, name = self._match_provider(model)
        if p and p.api_base:
            return p.api_base
        if name:
            spec = find_by_name(name)
            if spec and spec.default_api_base:
                return spec.default_api_base
        return None

    model_config = ConfigDict(env_prefix="SUN_AGENT_", env_nested_delimiter="__")
