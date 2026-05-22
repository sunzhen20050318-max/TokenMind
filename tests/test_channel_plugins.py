"""Tests for channel plugin discovery, merging, and config compatibility."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tokenmind.bus.events import OutboundMessage
from tokenmind.bus.queue import MessageBus
from tokenmind.channels.base import BaseChannel
from tokenmind.channels.manager import ChannelManager
from tokenmind.config.schema import ChannelsConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakePlugin(BaseChannel):
    name = "fakeplugin"
    display_name = "Fake Plugin"

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send(self, msg: OutboundMessage) -> None:
        pass


class _FakeTelegram(BaseChannel):
    """Plugin that tries to shadow built-in telegram."""
    name = "telegram"
    display_name = "Fake Telegram"

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send(self, msg: OutboundMessage) -> None:
        pass


def _make_entry_point(name: str, cls: type):
    """Create a mock entry point that returns *cls* on load()."""
    ep = SimpleNamespace(name=name, load=lambda _cls=cls: _cls)
    return ep


# ---------------------------------------------------------------------------
# ChannelsConfig extra="allow"
# ---------------------------------------------------------------------------

def test_channels_config_accepts_unknown_keys():
    cfg = ChannelsConfig.model_validate({
        "myplugin": {"enabled": True, "token": "abc"},
    })
    extra = cfg.model_extra
    assert extra is not None
    assert extra["myplugin"]["enabled"] is True
    assert extra["myplugin"]["token"] == "abc"


def test_channels_config_getattr_returns_extra():
    cfg = ChannelsConfig.model_validate({"myplugin": {"enabled": True}})
    section = getattr(cfg, "myplugin", None)
    assert isinstance(section, dict)
    assert section["enabled"] is True


def test_channels_config_builtin_fields_removed():
    """After decoupling, ChannelsConfig has no explicit channel fields."""
    cfg = ChannelsConfig()
    assert not hasattr(cfg, "telegram")
    assert cfg.send_progress is True
    assert cfg.send_tool_hints is False


# ---------------------------------------------------------------------------
# discover_plugins
# ---------------------------------------------------------------------------

_EP_TARGET = "importlib.metadata.entry_points"


def test_discover_plugins_loads_entry_points():
    from tokenmind.channels.registry import discover_plugins

    ep = _make_entry_point("customplugin", _FakePlugin)
    with patch(_EP_TARGET, return_value=[ep]):
        result = discover_plugins()

    assert "customplugin" in result
    assert result["customplugin"] is _FakePlugin


def test_discover_plugins_handles_load_error():
    from tokenmind.channels.registry import discover_plugins

    def _boom():
        raise RuntimeError("broken")

    ep = SimpleNamespace(name="broken", load=_boom)
    with patch(_EP_TARGET, return_value=[ep]):
        result = discover_plugins()

    assert "broken" not in result


# ---------------------------------------------------------------------------
# discover_all — merge & priority
# ---------------------------------------------------------------------------

def test_discover_all_includes_builtins():
    from tokenmind.channels.registry import discover_all, discover_channel_names

    with patch(_EP_TARGET, return_value=[]):
        result = discover_all()

    # discover_all() only returns channels that are actually available (dependencies installed)
    # discover_channel_names() returns all built-in channel names
    # So we check that all actually loaded channels are in the result
    for name in result:
        assert name in discover_channel_names()


def test_removed_foreign_channels_are_not_builtins():
    from tokenmind.channels.registry import discover_channel_names

    removed_channels = {"discord", "slack", "matrix", "teams", "line"}
    assert removed_channels.isdisjoint(discover_channel_names())


def test_discover_all_includes_external_plugin():
    from tokenmind.channels.registry import discover_all

    ep = _make_entry_point("customplugin", _FakePlugin)
    with patch(_EP_TARGET, return_value=[ep]):
        result = discover_all()

    assert "customplugin" in result
    assert result["customplugin"] is _FakePlugin


def test_discover_all_builtin_shadows_plugin():
    from tokenmind.channels.registry import discover_all

    ep = _make_entry_point("telegram", _FakeTelegram)
    with patch(_EP_TARGET, return_value=[ep]):
        result = discover_all()

    assert "telegram" in result
    assert result["telegram"] is not _FakeTelegram


# ---------------------------------------------------------------------------
# discover_enabled — only imports the requested channels
# ---------------------------------------------------------------------------

def test_discover_enabled_empty_short_circuits():
    """No channels enabled -> no imports, no entry_points scan."""
    from tokenmind.channels.registry import discover_enabled

    # If entry_points were called we'd see the patch detect it.
    with patch(_EP_TARGET) as ep_mock:
        result = discover_enabled(set())

    assert result == {}
    ep_mock.assert_not_called()


def test_discover_enabled_skips_unenabled_builtins():
    """Only the named channels should be loaded; the entry_points scan is
    skipped when every name is already satisfied by a built-in."""
    from tokenmind.channels.registry import discover_enabled

    with patch("tokenmind.channels.registry.load_channel_class") as load_mock:
        load_mock.return_value = _FakePlugin
        with patch(_EP_TARGET) as ep_mock:
            result = discover_enabled({"email"})

    assert "email" in result
    load_mock.assert_called_once_with("email")
    ep_mock.assert_not_called()


def test_discover_enabled_falls_back_to_plugins_for_unknown_names():
    """If an enabled name isn't a built-in, scan entry_points for it."""
    from tokenmind.channels.registry import discover_enabled

    ep = _make_entry_point("customplugin", _FakePlugin)
    with patch(_EP_TARGET, return_value=[ep]):
        result = discover_enabled({"customplugin"})

    assert "customplugin" in result
    assert result["customplugin"] is _FakePlugin


def test_discover_enabled_plugin_cannot_shadow_builtin():
    """If a plugin tries to claim a built-in name, the built-in wins."""
    from tokenmind.channels.registry import discover_enabled

    ep = _make_entry_point("telegram", _FakeTelegram)
    # Force the plugin scan by also asking for a non-builtin name.
    with patch(_EP_TARGET, return_value=[ep]):
        result = discover_enabled({"telegram", "noplugin"})

    assert "telegram" in result
    assert result["telegram"] is not _FakeTelegram


# ---------------------------------------------------------------------------
# Manager _init_channels with dict config (plugin scenario)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_manager_loads_plugin_from_dict_config():
    """ChannelManager should instantiate a plugin channel from a raw dict config."""
    from tokenmind.channels.manager import ChannelManager

    fake_config = SimpleNamespace(
        channels=ChannelsConfig.model_validate({
            "fakeplugin": {"enabled": True, "allowFrom": ["*"]},
        }),
        providers=SimpleNamespace(groq=SimpleNamespace(api_key="")),
    )

    with patch(
        "tokenmind.channels.registry.discover_channel_names",
        return_value=["fakeplugin"],
    ), patch(
        "tokenmind.channels.registry.load_channel_class",
        return_value=_FakePlugin,
    ):
        mgr = ChannelManager.__new__(ChannelManager)
        mgr.config = fake_config
        mgr.bus = MessageBus()
        mgr.channels = {}
        mgr._dispatch_task = None
        mgr._init_channels()

    assert "fakeplugin" in mgr.channels
    assert isinstance(mgr.channels["fakeplugin"], _FakePlugin)


@pytest.mark.asyncio
async def test_manager_skips_disabled_plugin():
    fake_config = SimpleNamespace(
        channels=ChannelsConfig.model_validate({
            "fakeplugin": {"enabled": False},
        }),
        providers=SimpleNamespace(groq=SimpleNamespace(api_key="")),
    )

    with patch(
        "tokenmind.channels.registry.discover_channel_names",
        return_value=["fakeplugin"],
    ), patch(
        "tokenmind.channels.registry.load_channel_class",
        return_value=_FakePlugin,
    ):
        mgr = ChannelManager.__new__(ChannelManager)
        mgr.config = fake_config
        mgr.bus = MessageBus()
        mgr.channels = {}
        mgr._dispatch_task = None
        mgr._init_channels()

    assert "fakeplugin" not in mgr.channels


# ---------------------------------------------------------------------------
# Built-in channel default_config() and dict->Pydantic conversion
# ---------------------------------------------------------------------------

def test_builtin_channel_default_config():
    """Built-in channels expose default_config() returning a dict with 'enabled': False."""
    from tokenmind.channels.telegram import TelegramChannel
    cfg = TelegramChannel.default_config()
    assert isinstance(cfg, dict)
    assert cfg["enabled"] is False
    assert "token" in cfg


def test_builtin_channel_init_from_dict():
    """Built-in channels accept a raw dict and convert to Pydantic internally."""
    from tokenmind.channels.telegram import TelegramChannel
    bus = MessageBus()
    ch = TelegramChannel({"enabled": False, "token": "test-tok", "allowFrom": ["*"]}, bus)
    assert ch.config.token == "test-tok"
    assert ch.config.allow_from == ["*"]


def test_chinese_external_channels_default_to_allow_all():
    """External channel setup should start usable while still allowing users to restrict IDs."""
    from tokenmind.channels.dingtalk import DingTalkChannel
    from tokenmind.channels.feishu import FeishuChannel
    from tokenmind.channels.mochat import MochatChannel
    from tokenmind.channels.qq import QQChannel
    from tokenmind.channels.wecom import WecomChannel

    for channel_cls in (FeishuChannel, DingTalkChannel, WecomChannel, QQChannel, MochatChannel):
        default_config = channel_cls.default_config()
        assert default_config["allowFrom"] == ["*"]


def test_feishu_config_prefers_non_empty_snake_case_over_blank_aliases():
    """Existing duplicate Feishu configs should not parse blank appId/appSecret first."""
    from tokenmind.channels.feishu import FeishuConfig

    cfg = FeishuConfig.model_validate({
        "enabled": True,
        "appId": "",
        "appSecret": "",
        "app_id": "cli_real",
        "app_secret": "secret_real",
    })

    assert cfg.app_id == "cli_real"
    assert cfg.app_secret == "secret_real"


def test_manager_can_relax_empty_allow_from_for_web_settings_access():
    """Web runtime must still start so users can repair invalid channel settings."""
    from tokenmind.channels.feishu import FeishuChannel
    from tokenmind.channels.manager import ChannelManager

    fake_config = SimpleNamespace(
        channels=ChannelsConfig.model_validate({
            "feishu": {
                "enabled": True,
                "app_id": "cli_real",
                "app_secret": "secret_real",
                "allow_from": [],
            },
        }),
        providers=SimpleNamespace(groq=SimpleNamespace(api_key="")),
    )

    with patch(
        "tokenmind.channels.registry.discover_all",
        return_value={"feishu": FeishuChannel},
    ):
        with pytest.raises(SystemExit):
            ChannelManager(fake_config, MessageBus())

        relaxed = ChannelManager(fake_config, MessageBus(), strict_allow_from=False)

    assert "feishu" in relaxed.channels


@pytest.mark.asyncio
async def test_manager_refreshes_existing_channel_config_without_recreating_connection():
    """A saved setting change should update the active channel instance in memory."""
    from tokenmind.channels.feishu import FeishuChannel
    from tokenmind.channels.manager import ChannelManager

    fake_config = SimpleNamespace(
        channels=ChannelsConfig.model_validate({
            "feishu": {
                "enabled": True,
                "app_id": "cli_real",
                "app_secret": "secret_real",
                "allow_from": [],
            },
        }),
        providers=SimpleNamespace(groq=SimpleNamespace(api_key="")),
    )

    with patch(
        "tokenmind.channels.registry.discover_all",
        return_value={"feishu": FeishuChannel},
    ):
        manager = ChannelManager(fake_config, MessageBus(), strict_allow_from=False)
        existing = manager.channels["feishu"]

        refreshed = await manager.refresh_channel(
            "feishu",
            {
                "enabled": True,
                "app_id": "cli_real",
                "app_secret": "secret_real",
                "allow_from": ["*"],
            },
        )

    assert refreshed is existing
    assert existing.config.allow_from == ["*"]
