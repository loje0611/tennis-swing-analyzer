"""Lightweight settings persistence (e.g. settings.json) for app restart survival."""
import json
import os

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "..", "settings.json")
DEFAULT_SETTINGS = {"tts_enabled": False}


def get_settings():
    """Read settings from disk. Returns dict with defaults for missing keys."""
    if not os.path.exists(SETTINGS_PATH):
        return DEFAULT_SETTINGS.copy()
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {**DEFAULT_SETTINGS, **data}
    except Exception:
        return DEFAULT_SETTINGS.copy()


def save_settings(tts_enabled=None, **kwargs):
    """Overwrite settings file. Pass tts_enabled=bool and/or other keys."""
    current = get_settings()
    if tts_enabled is not None:
        current["tts_enabled"] = bool(tts_enabled)
    current.update(kwargs)
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
    except Exception:
        pass
