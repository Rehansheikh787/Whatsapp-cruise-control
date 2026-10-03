"""
config/settings.py

Centralized configuration, runtime safety switches, and dynamic allowlist enforcement.
Exposes:
  - load_settings() -> dict: Safely reads config/settings.json with resilient fallback defaults.
  - is_dry_run() -> bool: Checks if dry-run simulation mode is active.
  - is_kill_switch_active() -> bool: Checks if kill_switch.flag exists in the repo root.
  - get_allowlist() -> set[str]: Derives allowed phone numbers directly from config/relationship_map.json.
  - enforce_allowlist(jid: str) -> bool: Verifies whether an incoming WhatsApp JID belongs to the allowlist.
"""

import json
from pathlib import Path

# Resolve repository root
REPO_ROOT = Path(__file__).resolve().parent.parent

# File paths
DEFAULT_SETTINGS_PATH = REPO_ROOT / "config" / "settings.json"
DEFAULT_RELATIONSHIP_MAP_PATH = REPO_ROOT / "config" / "relationship_map.json"
KILL_SWITCH_FLAG_PATH = REPO_ROOT / "kill_switch.flag"

# Safe default settings
DEFAULT_SETTINGS: dict = {
    "dry_run": True,
    "min_delay_seconds": 3,
    "max_delay_seconds": 12,
}


def load_settings(settings_path: str | Path | None = None) -> dict:
    """
    Reads configuration from config/settings.json.
    Returns safe default dictionary if file is missing or fails to parse.
    Never raises an exception to the caller.
    """
    path = Path(settings_path) if settings_path else DEFAULT_SETTINGS_PATH

    if not path.exists():
        return dict(DEFAULT_SETTINGS)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                # Merge with defaults so any missing key is safely populated
                merged = dict(DEFAULT_SETTINGS)
                merged.update(data)
                return merged
            return dict(DEFAULT_SETTINGS)
    except Exception:
        return dict(DEFAULT_SETTINGS)


def is_dry_run(settings_path: str | Path | None = None) -> bool:
    """
    Checks whether dry-run mode is enabled using load_settings().
    Defaults to True for maximum safety.
    """
    return bool(load_settings(settings_path).get("dry_run", True))


def is_kill_switch_active(repo_root: str | Path | None = None) -> bool:
    """
    Checks whether kill_switch.flag exists in the repository root.
    When active, all automated message sending should be halted immediately.
    """
    flag_path = (Path(repo_root) / "kill_switch.flag") if repo_root else KILL_SWITCH_FLAG_PATH
    return flag_path.exists()


def get_allowlist(map_path: str | Path | None = None) -> set[str]:
    """
    Reads config/relationship_map.json and returns a set of every contact key whose
    value is NOT 'unknown' and is not the literal '_default' key.
    Derived dynamically from your existing relationship mapping to prevent drift.
    """
    path = Path(map_path) if map_path else DEFAULT_RELATIONSHIP_MAP_PATH

    if not path.exists():
        return set()

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return set()

        allowlist = set()
        for key, val in data.items():
            k_str = str(key).strip()
            # Ignore the default fallback key
            if k_str == "_default":
                continue
            # Keep only known relationships (not 'unknown')
            if str(val).strip().lower() != "unknown" and k_str:
                allowlist.add(k_str)

        return allowlist
    except Exception:
        return set()


def enforce_allowlist(jid: str, map_path: str | Path | None = None) -> bool:
    """
    Strips the JID suffix (everything after the first '@', consistent with agent/router.py)
    and returns True only if that extracted phone number is present in get_allowlist().
    """
    if not jid or not isinstance(jid, str):
        return False

    clean_jid = jid.strip()
    if not clean_jid:
        return False

    # Extract number prefix before '@' (handles @s.whatsapp.net, @lid, @g.us, etc.)
    if "@" in clean_jid:
        number = clean_jid.split("@", 1)[0].strip()
    else:
        number = clean_jid

    if not number:
        return False

    return number in get_allowlist(map_path)
