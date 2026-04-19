"""Provider registry: single source of truth for model routing metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProviderSpec:
    """One provider's routing metadata."""

    name: str
    keywords: tuple[str, ...]
    display_name: str = ""
    backend: str = "openai_compat"  # openai_compat / anthropic / azure_openai / openai_codex

    is_gateway: bool = False
    is_local: bool = False
    detect_by_key_prefix: str = ""
    detect_by_base_keyword: str = ""
    default_api_base: str = ""

    strip_model_prefix: bool = False
    model_overrides: tuple[tuple[str, dict[str, Any]], ...] = ()
    prompt_caching_model_patterns: tuple[str, ...] = ()

    is_oauth: bool = False
    is_direct: bool = False
    supports_prompt_caching: bool = False

    @property
    def label(self) -> str:
        return self.display_name or self.name.title()


PROVIDERS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        name="custom",
        keywords=(),
        display_name="Custom",
        backend="openai_compat",
        default_api_base="http://localhost:8000/v1",
        is_direct=True,
    ),
    ProviderSpec(
        name="azure_openai",
        keywords=("azure", "azure-openai"),
        display_name="Azure OpenAI",
        backend="azure_openai",
        is_direct=True,
    ),
    ProviderSpec(
        name="openrouter",
        keywords=("openrouter",),
        display_name="OpenRouter",
        backend="openai_compat",
        is_gateway=True,
        detect_by_key_prefix="sk-or-",
        detect_by_base_keyword="openrouter",
        default_api_base="https://openrouter.ai/api/v1",
        supports_prompt_caching=True,
        prompt_caching_model_patterns=("claude",),
    ),
    ProviderSpec(
        name="aihubmix",
        keywords=("aihubmix",),
        display_name="AiHubMix",
        backend="openai_compat",
        is_gateway=True,
        detect_by_base_keyword="aihubmix",
        default_api_base="https://aihubmix.com/v1",
        strip_model_prefix=True,
    ),
    ProviderSpec(
        name="siliconflow",
        keywords=("siliconflow",),
        display_name="SiliconFlow",
        backend="openai_compat",
        is_gateway=True,
        detect_by_base_keyword="siliconflow",
        default_api_base="https://api.siliconflow.cn/v1",
    ),
    ProviderSpec(
        name="volcengine",
        keywords=("volcengine", "volces", "ark"),
        display_name="VolcEngine",
        backend="openai_compat",
        is_gateway=True,
        detect_by_base_keyword="volces",
        default_api_base="https://ark.cn-beijing.volces.com/api/v3",
    ),
    ProviderSpec(
        name="volcengine_coding_plan",
        keywords=("volcengine-plan",),
        display_name="VolcEngine Coding Plan",
        backend="openai_compat",
        is_gateway=True,
        default_api_base="https://ark.cn-beijing.volces.com/api/coding/v3",
        strip_model_prefix=True,
    ),
    ProviderSpec(
        name="byteplus",
        keywords=("byteplus",),
        display_name="BytePlus",
        backend="openai_compat",
        is_gateway=True,
        detect_by_base_keyword="bytepluses",
        default_api_base="https://ark.ap-southeast.bytepluses.com/api/v3",
        strip_model_prefix=True,
    ),
    ProviderSpec(
        name="byteplus_coding_plan",
        keywords=("byteplus-plan",),
        display_name="BytePlus Coding Plan",
        backend="openai_compat",
        is_gateway=True,
        default_api_base="https://ark.ap-southeast.bytepluses.com/api/coding/v3",
        strip_model_prefix=True,
    ),
    ProviderSpec(
        name="anthropic",
        keywords=("anthropic", "claude"),
        display_name="Anthropic",
        backend="anthropic",
        default_api_base="https://api.anthropic.com/v1/",
        supports_prompt_caching=True,
    ),
    ProviderSpec(
        name="openai",
        keywords=("openai", "gpt"),
        display_name="OpenAI",
        backend="openai_compat",
        default_api_base="https://api.openai.com/v1",
    ),
    ProviderSpec(
        name="openai_codex",
        keywords=("openai-codex",),
        display_name="OpenAI Codex",
        backend="openai_codex",
        default_api_base="https://chatgpt.com/backend-api",
        is_oauth=True,
    ),
    ProviderSpec(
        name="github_copilot",
        keywords=("github_copilot", "copilot"),
        display_name="Github Copilot",
        backend="openai_compat",
        default_api_base="https://api.githubcopilot.com",
        is_oauth=True,
    ),
    ProviderSpec(
        name="deepseek",
        keywords=("deepseek",),
        display_name="DeepSeek",
        backend="openai_compat",
        default_api_base="https://api.deepseek.com",
    ),
    ProviderSpec(
        name="gemini",
        keywords=("gemini",),
        display_name="Gemini",
        backend="openai_compat",
        default_api_base="https://generativelanguage.googleapis.com/v1beta/openai/",
    ),
    ProviderSpec(
        name="zhipu",
        keywords=("zhipu", "glm", "zai"),
        display_name="Zhipu AI",
        backend="openai_compat",
        default_api_base="https://open.bigmodel.cn/api/paas/v4/",
    ),
    ProviderSpec(
        name="dashscope",
        keywords=("qwen", "dashscope"),
        display_name="DashScope",
        backend="openai_compat",
        default_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
    ProviderSpec(
        name="moonshot",
        keywords=("moonshot", "kimi"),
        display_name="Moonshot",
        backend="openai_compat",
        default_api_base="https://api.moonshot.ai/v1",
        model_overrides=(("kimi-k2.5", {"temperature": 1.0}),),
    ),
    ProviderSpec(
        name="minimax",
        keywords=("minimax",),
        display_name="MiniMax",
        backend="openai_compat",
        default_api_base="https://api.minimax.io/v1",
    ),
    ProviderSpec(
        name="vllm",
        keywords=("vllm",),
        display_name="vLLM/Local",
        backend="openai_compat",
        is_local=True,
        default_api_base="http://localhost:8000/v1",
        strip_model_prefix=True,
    ),
    ProviderSpec(
        name="ollama",
        keywords=("ollama", "nemotron"),
        display_name="Ollama",
        backend="openai_compat",
        is_local=True,
        detect_by_base_keyword="11434",
        default_api_base="http://localhost:11434/v1",
        strip_model_prefix=True,
    ),
    ProviderSpec(
        name="groq",
        keywords=("groq",),
        display_name="Groq",
        backend="openai_compat",
        default_api_base="https://api.groq.com/openai/v1",
    ),
)


def find_by_name(name: str) -> ProviderSpec | None:
    """Find a provider spec by config field name, e.g. ``dashscope``."""
    for spec in PROVIDERS:
        if spec.name == name:
            return spec
    return None
