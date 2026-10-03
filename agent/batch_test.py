"""
agent/batch_test.py

End-to-end batch test harness for WhatsApp Cruise Control.
Exercises and validates every tier of the reply-or-ignore pipeline:
  - Hard Rules: own message, group message, unknown number
  - Signal Rules: media-only, forwarded message, one-word ack
  - Intent Check: money / financial emergency
  - Passed Gates: genuine casual and professional interactions with live generation

Summary table printed at the end summarizes:
  [Message (truncated), Relationship, Decision, Reason, Reply]
"""

import sys
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

from agent.decision_engine import should_reply
from agent.generator import generate_reply
from agent.router import resolve_relationship

# -----------------------------------------------------------------------------
# Test Suite Definition (10 realistic cases exercising every pipeline gate)
# -----------------------------------------------------------------------------
BATCH_TEST_CASES = [
    {
        "category": "Hard Rule: Own Message",
        "jid": "918082667601@s.whatsapp.net",
        "message": {
            "from_me": True,
            "text": "Haan bhai main nikal raha hu room se abhi.",
            "message_type": "text",
            "is_forwarded": False,
        },
    },
    {
        "category": "Hard Rule: Group Chat",
        "jid": "1203630252999901@g.us",
        "message": {
            "from_me": False,
            "text": "Everyone please note tomorrow's lab session is rescheduled to 3 PM.",
            "message_type": "text",
            "is_forwarded": False,
        },
    },
    {
        "category": "Hard Rule: Unknown Sender",
        "jid": "919999988888@s.whatsapp.net",
        "message": {
            "from_me": False,
            "text": "Hello, we have pre-approved instant personal loan offers for you.",
            "message_type": "text",
            "is_forwarded": False,
        },
    },
    {
        "category": "Signal Rule: Media Only (No Caption)",
        "jid": "918082667601@s.whatsapp.net",
        "message": {
            "from_me": False,
            "text": "",
            "message_type": "image",
            "is_forwarded": False,
        },
    },
    {
        "category": "Signal Rule: Forwarded Message",
        "jid": "918082667601@s.whatsapp.net",
        "message": {
            "from_me": False,
            "text": "Forwarded announcement: Heavy rainfall alert in Pune, stay indoors.",
            "message_type": "text",
            "is_forwarded": True,
        },
    },
    {
        "category": "Signal Rule: One-Word Ack",
        "jid": "918082667601@s.whatsapp.net",
        "message": {
            "from_me": False,
            "text": "thanks!",
            "message_type": "text",
            "is_forwarded": False,
        },
    },
    {
        "category": "Intent Check: Money / Financial Request",
        "jid": "918082667601@s.whatsapp.net",
        "message": {
            "from_me": False,
            "text": "Bhai urgent 5000 rupees GPay kar sakta hai kya? Kal sham tak pakka return kar dunga.",
            "message_type": "text",
            "is_forwarded": False,
        },
    },
    {
        "category": "Pass Gate: Friend Casual Query",
        "jid": "918082667601@s.whatsapp.net",
        "message": {
            "from_me": False,
            "text": "kaha hai bhai? Shaam ko badminton khelne chalna hai kya?",
            "message_type": "text",
            "is_forwarded": False,
        },
    },
    {
        "category": "Pass Gate: Professional Mentor Instruction",
        "jid": "919060078806@s.whatsapp.net",
        "message": {
            "from_me": False,
            "text": "Please submit the updated project report by tomorrow morning.",
            "message_type": "text",
            "is_forwarded": False,
        },
    },
    {
        "category": "Pass Gate: Friend Academic / Syllabus Chat",
        "jid": "917387131855@s.whatsapp.net",
        "message": {
            "from_me": False,
            "text": "Bhai kal ke unit test ka syllabus kya hai? Notes bhej de na.",
            "message_type": "text",
            "is_forwarded": False,
        },
    },
]


def run_batch_test():
    print("=" * 110)
    print("                       WHATSAPP CRUISE CONTROL: PIPELINE BATCH TEST                          ")
    print("=" * 110)

    results = []

    for idx, tc in enumerate(BATCH_TEST_CASES, start=1):
        cat = tc["category"]
        jid = tc["jid"]
        msg = tc["message"]
        raw_text = msg.get("text", "")

        # 1. Resolve relationship using agent/router.py
        rel, collection_name = resolve_relationship(jid)

        print(f"\n--- [Test #{idx}: {cat}] ---")
        print(f"  JID          : {jid}")
        print(f"  Relationship : {rel.upper()} (collection: {collection_name})")
        print(f"  Message Type : {msg.get('message_type')}, From Me: {msg.get('from_me')}, Forwarded: {msg.get('is_forwarded')}")
        print(f"  Message Text : \"{raw_text}\"")

        # 2. Layered reply-or-ignore pipeline via agent/decision_engine.py
        decision_res = should_reply(msg, rel)
        decision_bool = decision_res[0]
        reason = decision_res[1]
        fixed_reply = getattr(decision_res, "reply", None)
        decision_str = "REPLY" if decision_bool else "IGNORE"

        print(f"  >> Decision  : [{decision_str}] (Reason: {reason})")

        # 3. Call generator only if passed all gates (skip LLM for media_ack rule)
        generated_reply = ""
        if decision_bool:
            if fixed_reply:
                generated_reply = fixed_reply
                print(f"  >> Rule-based Ack Emoji : \"{generated_reply}\" (No LLM)")
            elif reason == "media_ack":
                generated_reply = "📸"
                print(f"  >> Rule-based Ack Emoji : \"{generated_reply}\" (No LLM)")
            else:
                print("  >> Calling Generator (persona + RAG)...")
                generated_reply = generate_reply(incoming_text=raw_text, relationship=rel)
                print(f"  >> Generated Reply : \"{generated_reply}\"")
        else:
            print("  >> Generator skipped (message filtered).")

        results.append({
            "idx": idx,
            "category": cat,
            "text": raw_text if raw_text else f"[{msg.get('message_type')} only]",
            "relationship": rel,
            "decision": decision_str,
            "reason": reason,
            "reply": generated_reply if generated_reply else "-",
        })

    # -------------------------------------------------------------------------
    # SUMMARY TABLE
    # -------------------------------------------------------------------------
    print("\n\n" + "=" * 118)
    print("                                          PIPELINE EXECUTION SUMMARY                                  ")
    print("=" * 118)
    header = f"{'#':<3} | {'Message (Truncated)':<32} | {'Rel':<12} | {'Decision':<8} | {'Reason':<32} | {'Reply'}"
    print(header)
    print("-" * 118)

    for r in results:
        # Truncate text nicely
        disp_text = r["text"].replace("\n", " ")
        if len(disp_text) > 30:
            disp_text = disp_text[:27] + "..."

        disp_reply = r["reply"].replace("\n", " ")
        if len(disp_reply) > 24:
            disp_reply = disp_reply[:21] + "..."

        disp_text_quoted = f'"{disp_text}"'
        row = (
            f"{r['idx']:<3} | "
            f"{disp_text_quoted:<32} | "
            f"{r['relationship']:<12} | "
            f"{r['decision']:<8} | "
            f"{r['reason']:<32} | "
            f"{disp_reply}"
        )
        print(row)

    print("=" * 118)
    print("\n[OK] Batch test run complete. All pipeline gates demonstrated.\n")


if __name__ == "__main__":
    run_batch_test()
