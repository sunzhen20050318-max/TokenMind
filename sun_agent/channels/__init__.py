"""Chat channels module with plugin architecture."""

from sun_agent.channels.base import BaseChannel
from sun_agent.channels.manager import ChannelManager

__all__ = ["BaseChannel", "ChannelManager"]
