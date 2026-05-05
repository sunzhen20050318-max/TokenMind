"""TokenMind Web UI Server."""

# Re-export the package version so /api/status reports the actual running
# release instead of a hand-maintained string that drifts out of sync.
from tokenmind import __version__

__all__ = ["__version__"]
