"""
agent/bridge.py

Flask HTTP bridge server connecting Node.js / Baileys WhatsApp client to the Python RAG agent.
Exposes a single POST /process endpoint on port 5001.

For each incoming message:
  1. Resolves relationship via agent.router.resolve_relationship
  2. Evaluates filters via agent.decision_engine.should_reply
  3. If approved, generates authentic reply via agent.generator.generate_reply
  4. Returns JSON {should_reply, reply, relationship, reason}
  5. Appends full trace to logs/console_feed.jsonl for the Streamlit Cruise Control Console
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Ensure UTF-8 console output on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from flask import Flask, jsonify, request

from agent.decision_engine import should_reply
from agent.generator import generate_reply
from agent.router import resolve_relationship
from ingestion.retrieval import retrieve_similar

logger = logging.getLogger("bridge")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

app = Flask(__name__)

# File logging paths
LOGS_DIR = REPO_ROOT / "logs"
CONSOLE_FEED_PATH = LOGS_DIR / "console_feed.jsonl"


def _log_console_feed(
    jid: str,
    relationship: str,
    decision: str,
    reason: str,
    reply: str | None,
    retrieval_trace: list[dict],
) -> None:
    """Appends an event to logs/console_feed.jsonl for the Streamlit dashboard."""
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "jid": jid,
            "relationship": relationship,
            "decision": decision,  # "reply" or "ignore"
            "reason": reason,
            "reply": reply,
            "retrieval_trace": retrieval_trace,
        }
        with open(CONSOLE_FEED_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error("Failed to append to console_feed.jsonl: %s", e)


@app.route("/process", methods=["POST"])
def process_message():
    """
    POST /process
    Accepts JSON:
      {
        "jid": str,
        "text": str,
        "message_type": str,
        "is_forwarded": bool,
        "from_me": bool
      }
    Returns JSON:
      {
        "should_reply": bool,
        "reply": str or null,
        "relationship": str,
        "reason": str
      }
    """
    data = request.get_json(force=True, silent=True) or {}

    jid = str(data.get("jid") or "").strip()
    raw_text = str(data.get("text") or "")
    message_type = str(data.get("message_type") or "text").strip().lower()
    is_forwarded = bool(data.get("is_forwarded", False))
    from_me = bool(data.get("from_me", False))

    message_dict = {
        "from_me": from_me,
        "text": raw_text,
        "message_type": message_type,
        "is_forwarded": is_forwarded,
    }

    # 1. Resolve relationship
    relationship, _ = resolve_relationship(jid)

    # 2. Evaluate layered reply-or-ignore pipeline
    decision_res = should_reply(message_dict, relationship)
    should_rep = decision_res[0]
    reason = decision_res[1]
    fixed_reply = getattr(decision_res, "reply", None)
    decision_str = "reply" if should_rep else "ignore"

    # 3. If approved, generate reply (pure rule-based ack for media_ack, LLM for text)
    reply_text = None
    if should_rep:
        if fixed_reply:
            reply_text = fixed_reply
        elif reason == "media_ack":
            media_emojis = {"image": "👍", "video": "👌", "audio": "👍"}
            reply_text = media_emojis.get(message_type, "👍")
        else:
            reply_text = generate_reply(incoming_text=raw_text, relationship=relationship)

    # 4. Fetch retrieval trace for console display / logging
    retrieval_trace = []
    if relationship != "group" and raw_text.strip() and reason != "media_ack":
        try:
            retrieval_trace = retrieve_similar(
                relationship=relationship,
                incoming_message=raw_text,
                k=3,
            )
        except Exception as e:
            logger.warning("Could not fetch retrieval trace for logging: %s", e)
            retrieval_trace = []

    # 5. Append to console_feed.jsonl regardless of outcome
    _log_console_feed(
        jid=jid,
        relationship=relationship,
        decision=decision_str,
        reason=reason,
        reply=reply_text,
        retrieval_trace=retrieval_trace,
    )

    # 6. Return response to caller (Node.js bridge)
    return jsonify({
        "should_reply": should_rep,
        "reply": reply_text,
        "relationship": relationship,
        "reason": reason,
    })


@app.route("/health", methods=["GET"])
def health():
    """Simple healthcheck endpoint."""
    return jsonify({"status": "ok", "service": "whatsapp_cruise_control_bridge"})


if __name__ == "__main__":
    logger.info("Starting WhatsApp Cruise Control Flask bridge server on port 5001 (debug=False)...")
    app.run(host="0.0.0.0", port=5001, debug=False)
