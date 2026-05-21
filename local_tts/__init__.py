from __future__ import annotations

try:
    from aqt import mw  # noqa: F401
except ImportError:
    mw = None

from .addon import LocalTTSAddon

_addon: LocalTTSAddon | None = None


def _bootstrap() -> None:
    global _addon
    if _addon is not None:
        return
    _addon = LocalTTSAddon()
    _addon.install()


if mw is not None:
    _bootstrap()
