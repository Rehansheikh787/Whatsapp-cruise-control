"""
agent/decision_engine.py

Layered reply-or-ignore pipeline for WhatsApp incoming messages.
Evaluates messages using a 4-tier filtering hierarchy (cheapest first):
  1. Hard Rules (instant, no LLM call)
  2. Signal Rules (instant text/media filters, no LLM call)
  3. Intent Check (Gemini LLM call via google-genai SDK, fails closed)
  4. Decision Passed (safe to reply)

Every decision is appended as a JSON line in logs/decision_log.jsonl.
"""

import dis
import json
import logging
import os
import string
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
from google import genai

from config.constants import ONE_WORD_ACKS

# Load environment variables
load_dotenv(REPO_ROOT / ".env")

# Set up logging for debugging unexpected responses
logger = logging.getLogger("decision_engine")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Paths
LOGS_DIR = REPO_ROOT / "logs"
DECISION_LOG_PATH = LOGS_DIR / "decision_log.jsonl"

# Model Configuration
MODEL_NAME = "gemini-3.5-flash"

# Natural conversational reaction emojis for incoming media messages (e.g. 👍, 👌 instead of gadget icons 📸, 🎥, 🎧)
MEDIA_ACK_EMOJIS = {
    "image": "👍",
    "video": "👌",
    "audio": "👍",
}
DEFAULT_MEDIA_ACK_EMOJI = "👍"


def get_media_ack_emoji(message_type: str, relationship: str = "friend") -> str:
    """Returns a natural conversational reaction emoji matching the media message."""
    rel = (relationship or "").strip().lower()
    mtype = (message_type or "").strip().lower()
    if rel == "professional":
        return "👍"
    return MEDIA_ACK_EMOJIS.get(mtype, DEFAULT_MEDIA_ACK_EMOJI)


class DecisionResult(tuple):
    """
    Subclass of tuple representing decision outcome.
    Can be unpacked as 2-tuple (should_reply, reason) or 3-tuple (should_reply, reason, reply).
    Also supports attribute access: .should_reply, .reason, .reply.
    """
    def __new__(cls, should_reply: bool, reason: str, reply: str | None = None):
        inst = super().__new__(cls, (should_reply, reason, reply) if reply is not None else (should_reply, reason, None))
        inst.should_reply = should_reply
        inst.reason = reason
        inst.reply = reply
        return inst

    def __iter__(self):
        try:
            frame = sys._getframe(1)
            code = frame.f_code
            lasti = frame.f_lasti
            for instr in dis.get_instructions(code):
                if instr.offset == lasti and "UNPACK" in instr.opname:
                    if instr.argval == 2:
                        return iter((self.should_reply, self.reason))
                    elif instr.argval == 3:
                        return iter((self.should_reply, self.reason, self.reply))
        except Exception:
            pass
        return iter((self.should_reply, self.reason))

    def __getitem__(self, index):
        if index == 0:
            return self.should_reply
        elif index == 1:
            return self.reason
        elif index == 2:
            return self.reply
        raise IndexError("DecisionResult index out of range")

    def __len__(self):
        return 3 if self.reply is not None else 2


# Initialize genai client once at module level
client = genai.Client()

INTENT_SYSTEM_PROMPT = """You are an intent classifier for an automated WhatsApp reply system.
Analyze the incoming message and classify it into EXACTLY ONE of these two labels:
- safe_to_auto_reply
- needs_human_money_or_serious

Classification Guidelines:
- Label as "needs_human_money_or_serious" if the message involves:
  * Money, payments, transfers, UPI, loans, financial transactions, or debts.
  * Medical emergencies, health concerns, hospital, doctor visits, or illness.
  * Legal issues, police, contracts, agreements, or official disputes.
  * Serious personal matters, emotional crises, grief, condolences, or relationship conflicts.
  * Urgent commitments, safety concerns, or anything requiring careful human judgment.
  * Any genuine ambiguity, sarcasm, or uncertainty where an auto-reply could cause confusion or harm.
- Label as "safe_to_auto_reply" if the message is:
  * Routine conversational inquiries, casual questions, greetings, coordination (e.g. meeting up, scheduling, study chats), banter, or general inquiries.

CRITICAL: Output ONLY the exact label name ("safe_to_auto_reply" or "needs_human_money_or_serious") in lowercase with NO additional words, punctuation, markdown formatting, or explanations.
"""


def _log_decision(message_text: str, relationship: str, decision: str, reason: str, reply: str | None = None) -> None:
    """Appends a decision entry to logs/decision_log.jsonl."""
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message text": message_text,
            "message_text": message_text,
            "relationship": relationship,
            "decision": decision,  # "reply" or "ignore"
            "reason": reason,
        }
        if reply:
            entry["reply"] = reply
        with open(DECISION_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error("Failed to append decision to log: %s", e)


def _classify_intent_with_llm(text: str) -> str:
    """
    Calls Gemini to classify message intent.
    Returns:
        "safe_to_auto_reply" or "needs_human_money_or_serious".
    Fails closed: returns "needs_human_money_or_serious" on any unexpected output or exception.
    """
    user_prompt = f"Message:\n\"\"\"{text}\"\"\""
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[INTENT_SYSTEM_PROMPT, user_prompt],
        )
        raw_text = (response.text or "").strip()
        cleaned_response = raw_text.strip("`'\"\n\r ")

        if cleaned_response in ("safe_to_auto_reply", "needs_human_money_or_serious"):
            return cleaned_response

        # Fail closed on unexpected string or formatting
        logger.warning(
            "Unexpected LLM intent classification output: %r. Failing closed to 'needs_human_money_or_serious'.",
            raw_text,
        )
        return "needs_human_money_or_serious"
    except Exception as e:
        logger.error(
            "Error calling LLM for intent classification: %s. Failing closed to 'needs_human_money_or_serious'.",
            e,
        )
        return "needs_human_money_or_serious"


def should_reply(message: dict, relationship: str) -> DecisionResult:
    """
    Evaluates whether an incoming message should be replied to or ignored.

    Args:
        message (dict): Message data dictionary containing:
            - from_me (bool): True if outgoing message sent by owner.
            - text (str): Message body or media caption.
            - message_type (str): Type of message ('text', 'image', 'audio', 'video', etc.).
            - is_forwarded (bool): True if the message was forwarded.
        relationship (str): Relationship classification ('friend', 'family', 'professional', 'group', 'unknown').

    Returns:
        DecisionResult: A tuple-compatible result (should_reply: bool, reason: str, reply: str | None).
    """
    msg_text = message.get("text") or ""
    msg_type = (message.get("message_type") or "text").strip().lower()
    from_me = bool(message.get("from_me", False))
    is_forwarded = bool(message.get("is_forwarded", False))
    rel = (relationship or "").strip().lower()

    # =========================================================================
    # LAYER 1: HARD RULES (instant, no LLM call)
    # =========================================================================
    if from_me:
        reason = "own message"
        _log_decision(msg_text, relationship, "ignore", reason)
        return DecisionResult(False, reason)

    if rel == "group":
        reason = "group chat, not allowlisted"
        _log_decision(msg_text, relationship, "ignore", reason)
        return DecisionResult(False, reason)

    if rel == "unknown":
        reason = "sender not in allowlisted"
        _log_decision(msg_text, relationship, "ignore", reason)
        return DecisionResult(False, reason)

    # =========================================================================
    # LAYER 2: SIGNAL RULES (instant heuristics, no LLM call)
    # =========================================================================
    has_text = bool(msg_text.strip())

    # Media-only rule (pure rule-based ack for allowlisted contacts; ignore for group/unknown)
    if msg_type in ("image", "audio", "video") and not has_text:
        if rel in ("group", "unknown"):
            reason = "media-only, sender not allowlisted or group"
            _log_decision(msg_text, relationship, "ignore", reason)
            return DecisionResult(False, reason)

        reason = "media_ack"
        ack_emoji = get_media_ack_emoji(msg_type, relationship)
        _log_decision(msg_text, relationship, "reply", reason, reply=ack_emoji)
        return DecisionResult(True, reason, ack_emoji)

    if is_forwarded:
        reason = "forwarded content, not a real question"
        _log_decision(msg_text, relationship, "ignore", reason)
        return DecisionResult(False, reason)

    # Check for low-signal acknowledgement (punctuation stripped)
    cleaned_ack_text = msg_text.translate(str.maketrans("", "", string.punctuation)).strip().lower()
    if cleaned_ack_text in ONE_WORD_ACKS:
        reason = "low-signal ack, no reply needed"
        _log_decision(msg_text, relationship, "ignore", reason)
        return DecisionResult(False, reason)

    # =========================================================================
    # LAYER 3: INTENT CHECK (one LLM call via google-genai, fails closed)
    # =========================================================================
    intent_label = _classify_intent_with_llm(msg_text)
    if intent_label != "safe_to_auto_reply":
        reason = "needs_human_money_or_serious"
        _log_decision(msg_text, relationship, "ignore", reason)
        return DecisionResult(False, reason)

    # =========================================================================
    # LAYER 4: PASSED ALL GATES
    # =========================================================================
    reason = "passed all gates"
    _log_decision(msg_text, relationship, "reply", reason)
    return DecisionResult(True, reason)

