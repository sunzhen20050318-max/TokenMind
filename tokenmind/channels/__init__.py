"""Chat channels module with plugin architecture."""

from tokenmind.channels.base import BaseChannel
from tokenmind.channels.manager import ChannelManager

__all__ = ["BaseChannel", "ChannelManager"]
