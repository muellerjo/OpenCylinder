"""OpenCylinder Manager — offline-first, multi-tenant management web app."""

from pathlib import Path


def _version() -> str:
    f = Path(__file__).resolve().parents[2] / "VERSION"          # manager/VERSION (source checkout)
    if f.is_file():
        return f.read_text().strip()
    try:
        from importlib.metadata import version
        return version("opencylinder-manager")
    except Exception:  # noqa: BLE001
        return "0+unknown"


__version__ = _version()
