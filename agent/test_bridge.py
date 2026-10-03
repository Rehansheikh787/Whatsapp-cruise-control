"""
agent/test_bridge.py

Unit tests for agent/bridge.py Flask server.
Uses Flask's test client to test /process and /health endpoints, mock dependencies,
and verify logs/console_feed.jsonl appending.
"""

import json
from unittest.mock import patch

import pytest

from agent.bridge import CONSOLE_FEED_PATH, app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"


def test_process_filtered_message(client):
    # Test own message ignored
    payload = {
        "jid": "918082667601@s.whatsapp.net",
        "text": "Hey I am testing my bridge",
        "message_type": "text",
        "is_forwarded": False,
        "from_me": True,
    }
    response = client.post("/process", json=payload)
    assert response.status_code == 200
    data = response.get_json()
    assert data["should_reply"] is False
    assert data["reply"] is None
    assert data["reason"] == "own message"

    # Verify line was written to console_feed.jsonl
    assert CONSOLE_FEED_PATH.exists()
    with open(CONSOLE_FEED_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
    last_entry = json.loads(lines[-1].strip())
    assert last_entry["jid"] == "918082667601@s.whatsapp.net"
    assert last_entry["decision"] == "ignore"
    assert last_entry["reason"] == "own message"


def test_process_reply_message(client):
    payload = {
        "jid": "918082667601@s.whatsapp.net",
        "text": "Bhai sham ko milte hai kya?",
        "message_type": "text",
        "is_forwarded": False,
        "from_me": False,
    }
    with patch("agent.bridge.should_reply", return_value=(True, "passed all gates")), \
         patch("agent.bridge.generate_reply", return_value="Haa bhai nikalta hu"), \
         patch("agent.bridge.retrieve_similar", return_value=[{"their_message": "kaha hai", "my_reply": "ghar pe", "distance": 1.0}]):
        
        response = client.post("/process", json=payload)
        assert response.status_code == 200
        data = response.get_json()
        assert data["should_reply"] is True
        assert data["reply"] == "Haa bhai nikalta hu"
        assert data["relationship"] == "friend"
        assert data["reason"] == "passed all gates"

        with open(CONSOLE_FEED_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        last_entry = json.loads(lines[-1].strip())
        assert last_entry["decision"] == "reply"
        assert last_entry["reply"] == "Haa bhai nikalta hu"
        assert len(last_entry["retrieval_trace"]) == 1
