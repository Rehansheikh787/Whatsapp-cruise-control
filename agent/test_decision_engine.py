"""
agent/test_decision_engine.py

Comprehensive tests for agent/decision_engine.py:
- Layer 1: Hard rules (from_me, group, unknown)
- Layer 2: Signal rules (media-only, forwarded, one-word acks)
- Layer 3: Intent check (money/serious, fail closed on unexpected output or exception)
- Layer 4: Passed all gates (safe to reply)
- Decision logging to logs/decision_log.jsonl
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from agent.decision_engine import (
    DECISION_LOG_PATH,
    _classify_intent_with_llm,
    should_reply,
)


@pytest.fixture(autouse=True)
def clean_log():
    """Ensure test runs don't interfere with previous logs."""
    yield


# =============================================================================
# LAYER 1: HARD RULES TESTS
# =============================================================================
def test_hard_rule_own_message():
    msg = {
        "from_me": True,
        "text": "Hey what's up?",
        "message_type": "text",
        "is_forwarded": False,
    }
    decision, reason = should_reply(msg, "friend")
    assert decision is False
    assert reason == "own message"


def test_hard_rule_group_chat():
    msg = {
        "from_me": False,
        "text": "Anyone free for dinner tonight?",
        "message_type": "text",
        "is_forwarded": False,
    }
    decision, reason = should_reply(msg, "group")
    assert decision is False
    assert reason == "group chat, not allowlisted"


def test_hard_rule_unknown_sender():
    msg = {
        "from_me": False,
        "text": "Hello, is this Rehan?",
        "message_type": "text",
        "is_forwarded": False,
    }
    decision, reason = should_reply(msg, "unknown")
    assert decision is False
    assert reason == "sender not in allowlisted"


# =============================================================================
# LAYER 2: SIGNAL RULES TESTS
# =============================================================================
def test_signal_rule_media_only_no_text():
    expected_emojis = {
        "image": "👍",
        "video": "👌",
        "audio": "👍",
    }
    # Allowlisted relationships: should return True with reason "media_ack" and fixed emoji
    for mtype, expected_emoji in expected_emojis.items():
        msg = {
            "from_me": False,
            "text": "",
            "message_type": mtype,
            "is_forwarded": False,
        }
        res = should_reply(msg, "friend")
        # 2-tuple unpacking
        decision, reason = res
        assert decision is True
        assert reason == "media_ack"
        assert res.reply == expected_emoji

        # 3-tuple unpacking
        d, r, reply = res
        assert d is True
        assert r == "media_ack"
        assert reply == expected_emoji

    # Unallowlisted relationships (group, unknown): must fall back to ignore
    for unallowlisted in ("group", "unknown"):
        for mtype in ("image", "video", "audio"):
            msg = {
                "from_me": False,
                "text": "",
                "message_type": mtype,
                "is_forwarded": False,
            }
            decision, reason = should_reply(msg, unallowlisted)
            assert decision is False
            assert "allowlisted" in reason or "group" in reason


def test_signal_rule_media_with_caption_proceeds(monkeypatch):
    # If media has text/caption, it should NOT trigger media-only rule
    monkeypatch.setattr("agent.decision_engine._classify_intent_with_llm", lambda text: "safe_to_auto_reply")
    msg = {
        "from_me": False,
        "text": "Check out this screenshot from our notes",
        "message_type": "image",
        "is_forwarded": False,
    }
    decision, reason = should_reply(msg, "friend")
    assert decision is True
    assert reason == "passed all gates"


def test_signal_rule_forwarded_message():
    msg = {
        "from_me": False,
        "text": "Forwarded announcement about college holiday",
        "message_type": "text",
        "is_forwarded": True,
    }
    decision, reason = should_reply(msg, "friend")
    assert decision is False
    assert reason == "forwarded content, not a real question"


def test_signal_rule_one_word_acks():
    ack_samples = ["ok", "Okay", "k", "kk", "haan", "hmm!", "Thanks.", "thank you!!", "cool...", "nice?"]
    for sample in ack_samples:
        msg = {
            "from_me": False,
            "text": sample,
            "message_type": "text",
            "is_forwarded": False,
        }
        decision, reason = should_reply(msg, "friend")
        assert decision is False, f"Failed for ack sample: {sample}"
        assert reason == "low-signal ack, no reply needed"


# =============================================================================
# LAYER 3 & 4: INTENT CHECK & PASS GATES
# =============================================================================
def test_intent_needs_human_money(monkeypatch):
    monkeypatch.setattr("agent.decision_engine._classify_intent_with_llm", lambda text: "needs_human_money_or_serious")
    msg = {
        "from_me": False,
        "text": "Bhai mujhe 2000 rupay gpay kar de emergency hai",
        "message_type": "text",
        "is_forwarded": False,
    }
    decision, reason = should_reply(msg, "friend")
    assert decision is False
    assert reason == "needs_human_money_or_serious"


def test_intent_fail_closed_on_unexpected_model_output(monkeypatch):
    # Mock LLM returning unexpected text (e.g. Markdown or extra explanation)
    fake_resp = MagicMock()
    fake_resp.text = "I think it is safe_to_auto_reply because it is friendly."
    with patch("agent.decision_engine.client.models.generate_content", return_value=fake_resp):
        res = _classify_intent_with_llm("Hey how are you?")
        assert res == "needs_human_money_or_serious"

    msg = {
        "from_me": False,
        "text": "Hey how are you?",
        "message_type": "text",
        "is_forwarded": False,
    }
    with patch("agent.decision_engine._classify_intent_with_llm", return_value="needs_human_money_or_serious"):
        decision, reason = should_reply(msg, "friend")
        assert decision is False
        assert reason == "needs_human_money_or_serious"


def test_intent_fail_closed_on_llm_exception():
    # Mock LLM raising network or API error
    with patch("agent.decision_engine.client.models.generate_content", side_effect=Exception("API connection timeout")):
        res = _classify_intent_with_llm("Hey how are you?")
        assert res == "needs_human_money_or_serious"


def test_passed_all_gates(monkeypatch):
    monkeypatch.setattr("agent.decision_engine._classify_intent_with_llm", lambda text: "safe_to_auto_reply")
    msg = {
        "from_me": False,
        "text": "Kal shaam ko badminton khelne chalna hai kya?",
        "message_type": "text",
        "is_forwarded": False,
    }
    decision, reason = should_reply(msg, "friend")
    assert decision is True
    assert reason == "passed all gates"


# =============================================================================
# DECISION LOGGING TESTS
# =============================================================================
def test_decision_log_jsonl_output(monkeypatch):
    monkeypatch.setattr("agent.decision_engine._classify_intent_with_llm", lambda text: "safe_to_auto_reply")
    test_text = "Unique test message for logging check 999888"
    msg = {
        "from_me": False,
        "text": test_text,
        "message_type": "text",
        "is_forwarded": False,
    }
    decision, reason = should_reply(msg, "friend")
    assert decision is True

    assert DECISION_LOG_PATH.exists()
    with open(DECISION_LOG_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()

    assert len(lines) > 0
    last_entry = json.loads(lines[-1].strip())
    assert last_entry["message text"] == test_text
    assert last_entry["relationship"] == "friend"
    assert last_entry["decision"] == "reply"
    assert last_entry["reason"] == "passed all gates"
    assert "timestamp" in last_entry
