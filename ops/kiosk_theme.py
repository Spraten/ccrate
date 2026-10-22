"""Shared, collection-scoped theme preference for the touchscreen UI."""
from __future__ import annotations

import json
import os
import pathlib
import tempfile
from uuid import UUID

THEMES = frozenset({
    "homebox", "light", "dark", "cupcake", "bumblebee", "emerald", "corporate",
    "synthwave", "retro", "cyberpunk", "valentine", "halloween", "garden", "forest",
    "aqua", "lofi", "pastel", "fantasy", "wireframe", "black", "luxury", "dracula",
    "cmyk", "autumn", "business", "acid", "lemonade", "night", "coffee", "winter",
})


def _path(root: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(root) / "work" / "ops" / "kiosk-themes.json"


def get_theme(root: pathlib.Path, group_id: str) -> str:
    group = str(UUID(str(group_id)))
    try:
        value = json.loads(_path(root).read_text(encoding="utf-8"))
        theme = value.get("themes", {}).get(group, "homebox")
        return theme if theme in THEMES else "homebox"
    except (OSError, ValueError, TypeError, AttributeError):
        return "homebox"


def set_theme(root: pathlib.Path, group_id: str, theme: str) -> str:
    group = str(UUID(str(group_id)))
    if not isinstance(theme, str) or theme not in THEMES:
        raise ValueError("Choose a theme available in Homebox.")
    path = _path(root)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
        themes = current.get("themes", {})
        if not isinstance(themes, dict):
            themes = {}
    except (OSError, ValueError, TypeError, AttributeError):
        themes = {}
    themes[group] = theme
    payload = json.dumps({"version": 1, "themes": themes}, sort_keys=True, separators=(",", ":"))
    descriptor, temporary = tempfile.mkstemp(prefix=".kiosk-themes-", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return theme
