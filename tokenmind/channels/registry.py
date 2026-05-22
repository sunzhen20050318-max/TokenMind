"""Auto-discovery for built-in channel modules and external plugins."""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from tokenmind.channels.base import BaseChannel

_INTERNAL = frozenset({"base", "manager", "registry"})


def discover_channel_names() -> list[str]:
    """Return all built-in channel module names by scanning the package (zero imports)."""
    import tokenmind.channels as pkg

    return [
        name
        for _, name, ispkg in pkgutil.iter_modules(pkg.__path__)
        if name not in _INTERNAL and not ispkg
    ]


def load_channel_class(module_name: str) -> type[BaseChannel]:
    """Import *module_name* and return the first BaseChannel subclass found."""
    from tokenmind.channels.base import BaseChannel as _Base

    mod = importlib.import_module(f"tokenmind.channels.{module_name}")
    for attr in dir(mod):
        obj = getattr(mod, attr)
        if isinstance(obj, type) and issubclass(obj, _Base) and obj is not _Base:
            return obj
    raise ImportError(f"No BaseChannel subclass in tokenmind.channels.{module_name}")


def discover_plugins() -> dict[str, type[BaseChannel]]:
    """Discover external channel plugins registered via entry_points."""
    from importlib.metadata import entry_points

    plugins: dict[str, type[BaseChannel]] = {}
    for ep in entry_points(group="tokenmind.channels"):
        try:
            cls = ep.load()
            plugins[ep.name] = cls
        except Exception as e:
            logger.warning("Failed to load channel plugin '{}': {}", ep.name, e)
    return plugins


def discover_enabled(enabled_names: set[str]) -> dict[str, type[BaseChannel]]:
    """Return only the channels whose module names are in *enabled_names*.

    Skips the cost of importing third-party SDKs (telegram, lark_oapi,
    dingtalk_stream, baileys) for channels the user hasn't turned on.
    Uses cheap ``pkgutil.iter_modules`` to enumerate built-in names first,
    then imports only those that match the enabled set. External plugins
    are likewise filtered by name and the ``entry_points`` scan is skipped
    entirely when every enabled name is already satisfied by a built-in
    (the entry-points walk itself costs ~100 ms on a typical install).

    Built-in channels take priority — an external plugin cannot shadow a
    built-in name.
    """
    if not enabled_names:
        return {}

    builtin: dict[str, type[BaseChannel]] = {}
    for modname in discover_channel_names():
        if modname not in enabled_names:
            continue
        try:
            builtin[modname] = load_channel_class(modname)
        except ImportError as e:
            logger.trace("Skipping built-in channel '{}': {}", modname, e)

    if enabled_names <= builtin.keys():
        return builtin

    external = discover_plugins()
    shadowed = set(external) & set(builtin)
    if shadowed:
        logger.warning("Plugin(s) shadowed by built-in channels (ignored): {}", shadowed)
    return {**{k: v for k, v in external.items() if k in enabled_names and k not in shadowed}, **builtin}


def discover_all() -> dict[str, type[BaseChannel]]:
    """Return every available channel — built-in + external plugins.

    This eagerly imports every channel module (including heavy third-party
    SDKs) and is intended for code paths that genuinely need the full
    catalog: ``tokenmind channels list``, the onboarding wizard, etc.
    Hot startup paths should call :func:`discover_enabled` instead.

    Built-in channels take priority — an external plugin cannot shadow a
    built-in name.
    """
    builtin: dict[str, type[BaseChannel]] = {}
    for modname in discover_channel_names():
        try:
            builtin[modname] = load_channel_class(modname)
        except ImportError as e:
            logger.trace("Skipping built-in channel '{}': {}", modname, e)

    external = discover_plugins()
    shadowed = set(external) & set(builtin)
    if shadowed:
        logger.warning("Plugin(s) shadowed by built-in channels (ignored): {}", shadowed)

    return {**external, **builtin}
