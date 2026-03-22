"""Config API endpoints."""

from __future__ import annotations

from pydantic import BaseModel

from fastapi import APIRouter, HTTPException

from sun_agent.config.loader import load_config, save_config

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


class ConfigResponse(BaseModel):
    """Response model for GET /api/config."""

    providers: dict
    defaults: dict


def _mask_api_key(api_key: str) -> str:
    """Mask an API key, showing only the last 4 characters."""
    if not api_key or len(api_key) <= 4:
        return "****"
    return "****" + api_key[-4:]


def _provider_config_to_dict(provider_name: str, provider_config: object) -> dict:
    """Convert a provider config to dict with masked api_key."""
    result = {
        "api_base": getattr(provider_config, "api_base", None),
        "extra_headers": getattr(provider_config, "extra_headers", None),
        "default_model": getattr(provider_config, "default_model", None),
    }
    api_key = getattr(provider_config, "api_key", "") or ""
    result["api_key"] = _mask_api_key(api_key)
    return result


@router.get("", response_model=ConfigResponse)
async def get_config():
    """Get the current configuration with masked API keys."""
    try:
        config = load_config()

        # Build providers dict with masked API keys
        providers_dict = {}
        for provider_name in dir(config.providers):
            if provider_name.startswith("_"):
                continue
            if provider_name == "model_fields":
                continue
            try:
                provider_config = getattr(config.providers, provider_name)
                if hasattr(provider_config, "api_key"):
                    providers_dict[provider_name] = _provider_config_to_dict(
                        provider_name, provider_config
                    )
            except Exception:
                continue

        # Build defaults dict
        defaults_dict = {
            "model": config.agents.defaults.model,
            "provider": config.agents.defaults.provider,
            "max_tokens": config.agents.defaults.max_tokens,
            "temperature": config.agents.defaults.temperature,
        }

        return ConfigResponse(providers=providers_dict, defaults=defaults_dict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load config: {e}")


@router.put("/providers/{provider}")
async def update_provider_config(provider: str, update: ProviderConfigUpdate):
    """Update a specific provider's configuration."""
    try:
        config = load_config()

        # Check if provider exists
        if not hasattr(config.providers, provider):
            raise HTTPException(
                status_code=404,
                detail=f"Provider '{provider}' not found",
            )

        provider_config = getattr(config.providers, provider)

        # Update fields if provided
        if update.api_key is not None:
            provider_config.api_key = update.api_key
        if update.api_base is not None:
            provider_config.api_base = update.api_base
        if update.extra_headers is not None:
            provider_config.extra_headers = update.extra_headers
        if update.default_model is not None:
            provider_config.default_model = update.default_model

        # Save config
        save_config(config)

        return {
            "success": True,
            "provider": provider,
            "config": _provider_config_to_dict(provider, provider_config),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update provider: {e}")


@router.put("/defaults")
async def update_defaults(update: DefaultsUpdate):
    """Update the default agent configuration."""
    try:
        config = load_config()

        # Update fields if provided
        if update.model is not None:
            config.agents.defaults.model = update.model
        if update.provider is not None:
            config.agents.defaults.provider = update.provider

        # Save config
        save_config(config)

        return {
            "success": True,
            "defaults": {
                "model": config.agents.defaults.model,
                "provider": config.agents.defaults.provider,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update defaults: {e}")