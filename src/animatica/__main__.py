"""Allow `python -m animatica ...` (works even when the `animatica` script is not on PATH)."""
from animatica.cli import app

if __name__ == "__main__":
    app()
