"""PyInstaller entrypoint for TokenMind macOS desktop builds."""

from tokenmind.desktop.launcher import main


if __name__ == "__main__":
    raise SystemExit(main())
