import json
import pytest
from pathlib import Path
from agent.router import resolve_relationship


@pytest.fixture
def custom_map(tmp_path):
    """Fixture providing a temporary isolated relationship_map.json."""
    map_data = {
        "_default": "unknown",
        "918082667601": "Friend",
        "919060078806": "Professional",
        "911122334455": "Family",
        "120363025342": "Friend"  # Group ID mistakenly in map to test priority
    }
    map_file = tmp_path / "relationship_map.json"
    with open(map_file, "w", encoding="utf-8") as f:
        json.dump(map_data, f)
    return str(map_file)


# ---------------------------------------------------------------------------
# 1. Known numbers from map resolve correctly
# ---------------------------------------------------------------------------
def test_known_number_s_whatsapp_net(custom_map):
    jid = "918082667601@s.whatsapp.net"
    rel, col = resolve_relationship(jid, map_path=custom_map)
    assert rel == "friend"
    assert col == "history_friend"


def test_known_number_lid_suffix(custom_map):
    jid = "919060078806@lid"
    rel, col = resolve_relationship(jid, map_path=custom_map)
    assert rel == "professional"
    assert col == "history_professional"


def test_known_number_plain_digits_without_suffix(custom_map):
    jid = "911122334455"
    rel, col = resolve_relationship(jid, map_path=custom_map)
    assert rel == "family"
    assert col == "history_family"


def test_known_number_against_production_config():
    """Verify against the actual config/relationship_map.json if present."""
    prod_path = "config/relationship_map.json"
    if Path(prod_path).exists():
        rel, col = resolve_relationship("918082667601@s.whatsapp.net", map_path=prod_path)
        assert rel == "friend"
        assert col == "history_friend"

        rel_prof, col_prof = resolve_relationship("919060078806@s.whatsapp.net", map_path=prod_path)
        assert rel_prof == "professional"
        assert col_prof == "history_professional"


# ---------------------------------------------------------------------------
# 2. Unknown numbers fall back to _default (or 'unknown')
# ---------------------------------------------------------------------------
def test_unknown_number_falls_back_to_default(custom_map):
    jid = "9999999999@s.whatsapp.net"
    rel, col = resolve_relationship(jid, map_path=custom_map)
    assert rel == "unknown"
    assert col == "history_unknown"


def test_unknown_number_with_custom_default(tmp_path):
    map_data = {"_default": "casual", "12345": "friend"}
    map_file = tmp_path / "map_custom_default.json"
    with open(map_file, "w", encoding="utf-8") as f:
        json.dump(map_data, f)

    rel, col = resolve_relationship("98765@s.whatsapp.net", map_path=str(map_file))
    assert rel == "casual"
    assert col == "history_casual"


def test_missing_default_in_map_falls_back_to_unknown(tmp_path):
    map_data = {"12345": "friend"}  # No "_default" key
    map_file = tmp_path / "map_no_default.json"
    with open(map_file, "w", encoding="utf-8") as f:
        json.dump(map_data, f)

    rel, col = resolve_relationship("99999@s.whatsapp.net", map_path=str(map_file))
    assert rel == "unknown"
    assert col == "history_unknown"


# ---------------------------------------------------------------------------
# 3. Group JIDs always return ("group", None)
# ---------------------------------------------------------------------------
def test_group_jid_returns_group_none(custom_map):
    jid = "120363025342898765@g.us"
    rel, col = resolve_relationship(jid, map_path=custom_map)
    assert rel == "group"
    assert col is None


def test_group_jid_ignores_map_even_if_number_is_present(custom_map):
    # '120363025342' is in custom_map tagged as 'Friend', but ending with @g.us must override
    jid = "120363025342@g.us"
    rel, col = resolve_relationship(jid, map_path=custom_map)
    assert rel == "group"
    assert col is None


# ---------------------------------------------------------------------------
# 4. Malformed / empty JIDs return safe fallback without crashing
# ---------------------------------------------------------------------------
def test_empty_string_jid(custom_map):
    rel, col = resolve_relationship("", map_path=custom_map)
    assert rel == "unknown"
    assert col == "history_unknown"


def test_whitespace_string_jid(custom_map):
    rel, col = resolve_relationship("   ", map_path=custom_map)
    assert rel == "unknown"
    assert col == "history_unknown"


def test_none_jid(custom_map):
    rel, col = resolve_relationship(None, map_path=custom_map)
    assert rel == "unknown"
    assert col == "history_unknown"


def test_missing_number_before_at(custom_map):
    rel, col = resolve_relationship("@s.whatsapp.net", map_path=custom_map)
    assert rel == "unknown"
    assert col == "history_unknown"


def test_non_existent_map_path_falls_back_gracefully():
    rel, col = resolve_relationship("918082667601@s.whatsapp.net", map_path="non_existent_file.json")
    assert rel == "unknown"
    assert col == "history_unknown"


# ---------------------------------------------------------------------------
# 5. Validation script tests (key formats, lengths, and _default)
# ---------------------------------------------------------------------------
from agent.validate_relationship_map import validate_relationship_map


def test_validate_relationship_map_valid_config():
    """Verify that current production config/relationship_map.json passes validation."""
    assert validate_relationship_map("config/relationship_map.json") is True


def test_validate_flags_copy_paste_symbols(tmp_path):
    """Flags keys containing '+', spaces, dashes, or letters."""
    bad_map = {
        "_default": "unknown",
        "+919876543210": "Friend",      # has '+'
        "91 98765 43210": "Friend",     # has spaces
        "9198-765-4321": "Friend",      # has dashes
        "contact_john": "Friend"        # has letters
    }
    p = tmp_path / "bad_symbols.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(bad_map, f)

    assert validate_relationship_map(p) is False


def test_validate_flags_implausible_lengths(tmp_path):
    """Flags keys with fewer than 8 or more than 15 digits."""
    bad_map = {
        "_default": "unknown",
        "12345": "Friend",                  # 5 digits (too short)
        "12345678901234567": "Friend"       # 17 digits (too long)
    }
    p = tmp_path / "bad_lengths.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(bad_map, f)

    assert validate_relationship_map(p) is False


def test_validate_flags_missing_or_invalid_default(tmp_path):
    """Flags missing _default or invalid typo values."""
    no_default = {"919876543210": "Friend"}
    p1 = tmp_path / "no_default.json"
    with open(p1, "w", encoding="utf-8") as f:
        json.dump(no_default, f)
    assert validate_relationship_map(p1) is False

    bad_default = {"_default": "casual_typo", "919876543210": "Friend"}
    p2 = tmp_path / "bad_default.json"
    with open(p2, "w", encoding="utf-8") as f:
        json.dump(bad_default, f)
    assert validate_relationship_map(p2) is False

