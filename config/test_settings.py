"""
config/test_settings.py

Unit tests for config/settings.py verifying load_settings defaults and resilience,
kill switch checking, dynamic allowlist extraction, and JID allowlist enforcement.
"""

import json
from pathlib import Path
import pytest

from config.settings import (
    DEFAULT_SETTINGS,
    enforce_allowlist,
    get_allowlist,
    is_dry_run,
    is_kill_switch_active,
    load_settings,
)


def test_load_settings_missing_file(tmp_path):
    missing_file = tmp_path / "non_existent.json"
    settings = load_settings(missing_file)
    assert settings == DEFAULT_SETTINGS
    assert settings["dry_run"] is True
    assert settings["min_delay_seconds"] == 3
    assert settings["max_delay_seconds"] == 12


def test_load_settings_corrupted_json(tmp_path):
    corrupted_file = tmp_path / "broken.json"
    corrupted_file.write_text("{invalid_json: true", encoding="utf-8")
    settings = load_settings(corrupted_file)
    assert settings == DEFAULT_SETTINGS


def test_load_settings_valid_file(tmp_path):
    valid_file = tmp_path / "settings.json"
    valid_file.write_text(json.dumps({"dry_run": False, "min_delay_seconds": 5}), encoding="utf-8")
    settings = load_settings(valid_file)
    assert settings["dry_run"] is False
    assert settings["min_delay_seconds"] == 5
    assert settings["max_delay_seconds"] == 12  # Populated from defaults


def test_is_dry_run(tmp_path):
    file1 = tmp_path / "s1.json"
    file1.write_text(json.dumps({"dry_run": False}), encoding="utf-8")
    assert is_dry_run(file1) is False

    file2 = tmp_path / "s2.json"
    file2.write_text(json.dumps({"dry_run": True}), encoding="utf-8")
    assert is_dry_run(file2) is True

    # Missing file defaults to True
    assert is_dry_run(tmp_path / "missing.json") is True


def test_is_kill_switch_active(tmp_path):
    assert is_kill_switch_active(repo_root=tmp_path) is False

    flag_file = tmp_path / "kill_switch.flag"
    flag_file.touch()
    assert is_kill_switch_active(repo_root=tmp_path) is True


def test_get_allowlist_filters_default_and_unknown(tmp_path):
    map_file = tmp_path / "relationship_map.json"
    test_map = {
        "_default": "unknown",
        "918082667601": "friend",
        "919060078806": "professional",
        "919999999999": "unknown",
        "917777777777": "Unknown",
        "918888888888": "Family",
    }
    map_file.write_text(json.dumps(test_map), encoding="utf-8")

    allowed = get_allowlist(map_file)
    assert "_default" not in allowed
    assert "919999999999" not in allowed
    assert "917777777777" not in allowed
    assert "918082667601" in allowed
    assert "919060078806" in allowed
    assert "918888888888" in allowed
    assert len(allowed) == 3


def test_enforce_allowlist(tmp_path):
    map_file = tmp_path / "relationship_map.json"
    test_map = {
        "_default": "unknown",
        "918082667601": "friend",
        "919999999999": "unknown",
    }
    map_file.write_text(json.dumps(test_map), encoding="utf-8")

    # Valid JIDs for allowlisted number
    assert enforce_allowlist("918082667601@s.whatsapp.net", map_path=map_file) is True
    assert enforce_allowlist("918082667601@lid", map_path=map_file) is True
    assert enforce_allowlist("918082667601", map_path=map_file) is True

    # Unknown number in map
    assert enforce_allowlist("919999999999@s.whatsapp.net", map_path=map_file) is False

    # Unmapped number
    assert enforce_allowlist("911234567890@s.whatsapp.net", map_path=map_file) is False

    # Group JID
    assert enforce_allowlist("1203630252999901@g.us", map_path=map_file) is False

    # Edge cases
    assert enforce_allowlist("", map_path=map_file) is False
    assert enforce_allowlist(None, map_path=map_file) is False
