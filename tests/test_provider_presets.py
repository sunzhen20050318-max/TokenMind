from tokenmind.config.schema import Config, ProvidersConfig
from tokenmind.providers.registry import PROVIDERS
from tokenmind.server.routes.config import _PROVIDER_DEFAULT_MODELS


SUPPORTED_PROVIDER_PRESETS = {
    "anthropic",
    "custom",
    "dashscope",
    "deepseek",
    "gemini",
    "mimo",
    "minimax",
    "moonshot",
    "ollama",
    "openai",
    "openrouter",
    "siliconflow",
    "zhipu",
}


def test_provider_presets_match_supported_frontend_set() -> None:
    assert set(ProvidersConfig.model_fields) == SUPPORTED_PROVIDER_PRESETS
    assert {spec.name for spec in PROVIDERS} == SUPPORTED_PROVIDER_PRESETS
    assert set(_PROVIDER_DEFAULT_MODELS) == SUPPORTED_PROVIDER_PRESETS


def test_removed_default_provider_falls_back_to_configured_supported_provider() -> None:
    config = Config.model_validate(
        {
            "agents": {"defaults": {"provider": "groq", "model": "llama-3.3-70b-versatile"}},
            "providers": {
                "deepseek": {"apiKey": "sk-deepseek"},
            },
        }
    )

    assert config.get_provider_name() == "deepseek"
    assert config.get_api_key() == "sk-deepseek"
