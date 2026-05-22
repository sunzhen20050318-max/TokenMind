"""Channel manager for coordinating chat channels."""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from tokenmind.bus.queue import MessageBus
from tokenmind.channels.base import BaseChannel
from tokenmind.config.schema import Config


class ChannelManager:
    """
    Manages chat channels and coordinates message routing.

    Responsibilities:
    - Initialize enabled channels (Telegram, WhatsApp, etc.)
    - Start/stop channels
    - Route outbound messages
    """

    def __init__(self, config: Config, bus: MessageBus, *, strict_allow_from: bool = True):
        self.config = config
        self.bus = bus
        self.strict_allow_from = strict_allow_from
        self.channels: dict[str, BaseChannel] = {}
        self._dispatch_task: asyncio.Task | None = None
        self._channel_tasks: dict[str, asyncio.Task] = {}

        self._init_channels()

    @staticmethod
    def _is_enabled(section: Any) -> bool:
        return (
            section.get("enabled", False)
            if isinstance(section, dict)
            else getattr(section, "enabled", False)
        )

    def _build_channel(self, name: str, cls: type[BaseChannel], section: Any) -> BaseChannel:
        channel = cls(section, self.bus)
        groq_provider = getattr(self.config.providers, "groq", None)
        channel.transcription_api_key = getattr(groq_provider, "api_key", "")
        logger.info("{} channel enabled", cls.display_name)
        return channel

    def _init_channels(self) -> None:
        """Initialize channels discovered via pkgutil scan + entry_points plugins.

        Walks ``config.channels`` first to learn which channels the user has
        enabled, then asks the registry to import only those modules. This
        avoids the multi-hundred-ms cost of loading heavy SDKs (lark_oapi,
        dingtalk_stream, baileys) for channels that are turned off — a
        common state on fresh installs.
        """
        from tokenmind.channels.registry import (
            discover_channel_names,
            discover_enabled,
        )

        enabled_names: set[str] = set()
        for name in discover_channel_names():
            section = getattr(self.config.channels, name, None)
            if section is None:
                continue
            if self._is_enabled(section):
                enabled_names.add(name)

        for name, cls in discover_enabled(enabled_names).items():
            section = getattr(self.config.channels, name, None)
            if section is None:
                continue
            try:
                self.channels[name] = self._build_channel(name, cls, section)
            except Exception as e:
                logger.warning("{} channel not available: {}", name, e)

        self._validate_allow_from()

    def _validate_allow_from(self) -> None:
        for name, ch in self.channels.items():
            if getattr(ch.config, "allow_from", None) == []:
                message = (
                    f'"{name}" has empty allowFrom (denies all). '
                    f'Set ["*"] to allow everyone, or add specific user IDs.'
                )
                if self.strict_allow_from:
                    raise SystemExit(f"Error: {message}")
                logger.warning(message)

    def start_channel_background(self, name: str) -> None:
        """Start one channel in the current event loop without blocking the caller."""
        channel = self.channels.get(name)
        if channel is None:
            return
        existing = self._channel_tasks.get(name)
        if existing and not existing.done():
            return
        self._channel_tasks[name] = asyncio.create_task(self._start_channel(name, channel))

    async def refresh_channel(self, name: str, section: dict[str, Any]) -> BaseChannel | None:
        """Apply saved channel settings to the running channel manager."""
        from tokenmind.channels.registry import discover_enabled

        cls = discover_enabled({name}).get(name)
        if cls is None:
            logger.warning("Cannot refresh unknown channel {}", name)
            return None

        existing = self.channels.get(name)
        if not self._is_enabled(section):
            if existing is not None:
                await existing.stop()
                self.channels.pop(name, None)
            task = self._channel_tasks.pop(name, None)
            if task and not task.done():
                task.cancel()
            return None

        replacement = self._build_channel(name, cls, section)
        if existing is not None:
            existing.config = replacement.config
            existing.transcription_api_key = replacement.transcription_api_key
            logger.info("{} channel config refreshed", name)
            return existing

        self.channels[name] = replacement
        self._validate_allow_from()
        try:
            self.start_channel_background(name)
        except RuntimeError:
            logger.debug("No running event loop; {} channel will start on next runtime start", name)
        return replacement

    async def _start_channel(self, name: str, channel: BaseChannel) -> None:
        """Start a channel and log any exceptions."""
        try:
            await channel.start()
        except Exception as e:
            logger.error("Failed to start channel {}: {}", name, e)

    async def start_all(self) -> None:
        """Start all channels and the outbound dispatcher."""
        if not self.channels:
            logger.warning("No channels enabled")
            return

        # Start outbound dispatcher
        self._dispatch_task = asyncio.create_task(self._dispatch_outbound())

        # Start channels
        tasks = []
        for name, channel in self.channels.items():
            logger.info("Starting {} channel...", name)
            tasks.append(asyncio.create_task(self._start_channel(name, channel)))

        # Wait for all to complete (they should run forever)
        await asyncio.gather(*tasks, return_exceptions=True)

    async def stop_all(self) -> None:
        """Stop all channels and the dispatcher."""
        logger.info("Stopping all channels...")

        # Stop dispatcher
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass

        # Stop all channels
        for task in self._channel_tasks.values():
            if not task.done():
                task.cancel()
        for task in self._channel_tasks.values():
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._channel_tasks.clear()

        for name, channel in self.channels.items():
            try:
                await channel.stop()
                logger.info("Stopped {} channel", name)
            except Exception as e:
                logger.error("Error stopping {}: {}", name, e)

    async def _dispatch_outbound(self) -> None:
        """Dispatch outbound messages to the appropriate channel."""
        logger.info("Outbound dispatcher started")

        while True:
            try:
                msg = await asyncio.wait_for(
                    self.bus.consume_outbound(),
                    timeout=1.0
                )

                if msg.metadata.get("_progress"):
                    if msg.metadata.get("_tool_hint") and not self.config.channels.send_tool_hints:
                        continue
                    if not msg.metadata.get("_tool_hint") and not self.config.channels.send_progress:
                        continue

                channel = self.channels.get(msg.channel)
                if channel:
                    try:
                        await channel.send(msg)
                    except Exception as e:
                        logger.error("Error sending to {}: {}", msg.channel, e)
                else:
                    logger.warning("Unknown channel: {}", msg.channel)

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    def get_channel(self, name: str) -> BaseChannel | None:
        """Get a channel by name."""
        return self.channels.get(name)

    def get_status(self) -> dict[str, Any]:
        """Get status of all channels."""
        return {
            name: {
                "enabled": True,
                "running": channel.is_running
            }
            for name, channel in self.channels.items()
        }

    @property
    def enabled_channels(self) -> list[str]:
        """Get list of enabled channel names."""
        return list(self.channels.keys())
