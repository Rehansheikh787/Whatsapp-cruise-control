#!/usr/bin/env python3
"""
parse_export.py

Parses exported WhatsApp chat logs into clean (their_message, my_reply) turns:
1. Loops over .txt files in data/raw_export/ using pathlib.Path.glob.
2. Derives conversation_id from file name (stripped prefix and slugified).
3. Parses timestamps supporting 12hr (AM/PM) and 24hr formats.
4. Preserves multi-line messages without dropping continuation lines.
5. Drops system/media notifications (media omitted, calls, deleted msgs, etc.).
6. Drops standalone one-word acknowledgements (ok, thanks, hmm, etc.).
7. Groups consecutive bursts from the same sender into a single turn.
8. Creates (their_message, my_reply) pairs where MY turn immediately follows.
9. Caps each conversation to the last 500 pairs.
10. Writes all pairs to data/processed_pairs.jsonl.
11. Prints a per-conversation summary and warnings.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Ensure project root is available in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.constants import ONE_WORD_ACKS

# Substrings indicating system, media, or non-text events (case-insensitive)
SYSTEM_FILTER_SUBSTRINGS = [
    "messages and calls are end-to-end encrypted",
    "<media omitted>",
    "media omitted",
    "image omitted",
    "video omitted",
    "audio omitted",
    "sticker omitted",
    "gif omitted",
    "document omitted",
    "contact card omitted",
    "missed voice call",
    "missed video call",
    "created group",
    "changed the subject",
    "added you",
    "changed this group's icon",
    "this message was deleted",
    "this message was deleted.",
    "you deleted this message",
    "you deleted this message.",
    "<this message was edited>",
    "this message was edited",
    "security code changed",
    "your security code with",
]

# Standalone one-word acknowledgements to drop when they form an entire message
ACKNOWLEDGEMENT_WORDS = ONE_WORD_ACKS

# Regex to match standard WhatsApp message headers:
# "DATE, TIME - SENDER: MESSAGE"
# Supports 12hr (AM/PM), 24hr, narrow non-breaking spaces (\u202f), and varying date formats
MESSAGE_HEADER_REGEX = re.compile(
    r"^(\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4},\s+\d{1,2}:\d{2}(?::\d{2})?(?:[\s\u202f]?[ap]m)?)\s+-\s+([^:]+?):\s+(.*)$",
    re.IGNORECASE,
)

# Regex to detect general timestamp lines (including system lines without sender colon)
TIMESTAMP_LINE_REGEX = re.compile(
    r"^(\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4},\s+\d{1,2}:\d{2}(?::\d{2})?(?:[\s\u202f]?[ap]m)?)\s+-\s+(.*)$",
    re.IGNORECASE,
)


def derive_conversation_id(filename: str) -> str:
    """
    Derives conversation_id by stripping 'WhatsApp Chat with ' prefix
    and '.txt' extension, then slugifying to lowercase-with-hyphens.
    """
    stem = filename
    if stem.lower().endswith(".txt"):
        stem = stem[:-4]

    prefix = "WhatsApp Chat with "
    if stem.startswith(prefix):
        stem = stem[len(prefix):]

    # Remove non-alphanumeric chars (keep spaces and hyphens)
    slug = re.sub(r"[^\w\s-]", "", stem).strip().lower()
    # Replace whitespace and repeated hyphens/underscores with a single hyphen
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug


def is_system_or_media_message(text: str) -> bool:
    """Checks whether the text represents a system notification or media omission."""
    text_lower = text.lower().strip()
    return any(sub in text_lower for sub in SYSTEM_FILTER_SUBSTRINGS)


def is_standalone_acknowledgement(text: str) -> bool:
    """Checks whether the text is purely a standalone acknowledgement (ignoring punctuation)."""
    # Strip leading/trailing punctuation and whitespace
    clean_text = re.sub(r"^[^\w]+|[^\w]+$", "", text.strip()).lower()
    return clean_text in ONE_WORD_ACKS


def parse_conversation_file(file_path: Path, my_name: str) -> list[dict]:
    """
    Parses a single WhatsApp chat export into filtered raw messages with timestamps:
    [{"sender": str, "text": str, "timestamp": str}, ...]
    """
    messages: list[dict] = []
    current_msg: dict | None = None

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            header_match = MESSAGE_HEADER_REGEX.match(line)
            if header_match:
                # Flush previous message if valid
                if current_msg is not None:
                    msg_text = current_msg["text"].strip()
                    if not is_system_or_media_message(msg_text) and not is_standalone_acknowledgement(msg_text):
                        messages.append({
                            "sender": current_msg["sender"],
                            "text": msg_text,
                            "timestamp": current_msg["timestamp"],
                        })
                    current_msg = None

                timestamp = header_match.group(1).strip()
                sender = header_match.group(2).strip()
                content = header_match.group(3)

                current_msg = {
                    "sender": sender,
                    "text": content,
                    "timestamp": timestamp,
                }
            else:
                # Check if this line is a system event with a timestamp but no sender colon
                # (e.g. "14/05/21, 9:05 am - Messages and calls are end-to-end encrypted...")
                if TIMESTAMP_LINE_REGEX.match(line):
                    # Flush previous message before skipping system event
                    if current_msg is not None:
                        msg_text = current_msg["text"].strip()
                        if not is_system_or_media_message(msg_text) and not is_standalone_acknowledgement(msg_text):
                            messages.append({
                                "sender": current_msg["sender"],
                                "text": msg_text,
                                "timestamp": current_msg["timestamp"],
                            })
                        current_msg = None
                    continue

                # Continuation line of the active message
                if current_msg is not None:
                    current_msg["text"] += "\n" + line.rstrip("\r\n")

        # Flush the final message
        if current_msg is not None:
            msg_text = current_msg["text"].strip()
            if not is_system_or_media_message(msg_text) and not is_standalone_acknowledgement(msg_text):
                messages.append({
                    "sender": current_msg["sender"],
                    "text": msg_text,
                    "timestamp": current_msg["timestamp"],
                })

    return messages


def group_consecutive_turns(messages: list[dict]) -> list[dict]:
    """
    Groups consecutive messages from the SAME sender into a single turn
    joined by newlines.
    """
    turns: list[dict] = []
    for msg in messages:
        if turns and turns[-1]["sender"] == msg["sender"]:
            turns[-1]["text"] += "\n" + msg["text"]
        else:
            turns.append({
                "sender": msg["sender"],
                "text": msg["text"],
                "timestamp": msg["timestamp"],
            })
    return turns


def extract_conversation_pairs(turns: list[dict], conversation_id: str, my_name: str, max_pairs: int = 500) -> list[dict]:
    """
    Extracts (their_message, my_reply) pairs where a turn from the OTHER person
    is immediately followed by a turn from ME. Keeps at most the last max_pairs.
    Filters out noise, long essays/forwarded emails (>100 words), and identical pairs.
    """
    pairs: list[dict] = []
    noise_patterns = ["omitted", "<media", "deleted"]

    for i in range(len(turns) - 1):
        turn_other = turns[i]
        turn_me = turns[i + 1]

        if turn_other["sender"] != my_name and turn_me["sender"] == my_name:
            their_text = turn_other["text"].strip()
            my_text = turn_me["text"].strip()

            # Skip empty messages
            if not their_text or not my_text:
                continue

            # Skip leaked noise patterns
            if any(term in their_text.lower() or term in my_text.lower() for term in noise_patterns):
                continue

            # Skip suspiciously long replies (>100 words, e.g. forwarded emails/essays)
            if len(my_text.split()) > 100:
                continue

            # Skip identical or near-identical messages (echoes/duplicates)
            norm_their = "".join(c.lower() for c in their_text if c.isalnum())
            norm_my = "".join(c.lower() for c in my_text if c.isalnum())
            if norm_their and norm_their == norm_my:
                continue

            pairs.append({
                "conversation_id": conversation_id,
                "their_message": their_text,
                "my_reply": my_text,
                "timestamp": turn_me["timestamp"],
            })

    # Apply cap: keep at most the last max_pairs per conversation (using file order)
    if len(pairs) > max_pairs:
        pairs = pairs[-max_pairs:]

    return pairs


def main() -> int:
    # Ensure Windows console supports UTF-8 characters
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Parse WhatsApp exports into structured conversation training pairs."
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Exact sender name as it appears in the chat exports (e.g. '@Rehan Sheikh')"
    )
    parser.add_argument(
        "--input-dir",
        default="data/raw_export",
        help="Directory containing raw .txt chat exports (default: data/raw_export)"
    )
    parser.add_argument(
        "--output",
        default="data/processed_pairs.jsonl",
        help="Output .jsonl path (default: data/processed_pairs.jsonl)"
    )
    parser.add_argument(
        "--max-pairs",
        type=int,
        default=500,
        help="Maximum pairs to keep per conversation (default: 500)"
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"ERROR: Input directory does not exist: {input_dir}", file=sys.stderr)
        return 1

    chat_files = sorted(input_dir.glob("*.txt"))
    if not chat_files:
        print(f"WARNING: No .txt files found in {input_dir}", file=sys.stderr)
        return 1

    all_pairs: list[dict] = []
    summary: list[dict] = []
    zero_pair_conversations: list[str] = []

    print("\n" + "=" * 65)
    print("WHATSAPP EXPORT INGESTION & PAIR EXTRACTION")
    print(f"Target Sender Name: '{args.name}'")
    print(f"Source Directory  : {input_dir}")
    print("=" * 65 + "\n")

    for file_path in chat_files:
        conv_id = derive_conversation_id(file_path.name)
        messages = parse_conversation_file(file_path, args.name)
        turns = group_consecutive_turns(messages)
        pairs = extract_conversation_pairs(turns, conv_id, args.name, max_pairs=args.max_pairs)

        all_pairs.extend(pairs)
        summary.append({
            "file": file_path.name,
            "conversation_id": conv_id,
            "raw_messages": len(messages),
            "turns": len(turns),
            "pairs_kept": len(pairs),
        })

        if len(pairs) == 0:
            zero_pair_conversations.append(file_path.name)

    # Write output to JSONL
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for pair in all_pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    # Print human-readable summary
    print(f"{'File Name':<42} | {'Conv ID':<22} | {'Pairs Kept':<10}")
    print("-" * 80)
    for s in summary:
        print(f"{s['file']:<42} | {s['conversation_id']:<22} | {s['pairs_kept']:<10}")
    print("-" * 80)
    print(f"Total Conversations Processed : {len(summary)}")
    print(f"Total Pairs Kept Across All   : {len(all_pairs)}")
    print(f"Output File Written           : {output_path}")

    if zero_pair_conversations:
        print("\n" + "!" * 65, file=sys.stderr)
        print("WARNING: The following conversations produced ZERO pairs:", file=sys.stderr)
        for fn in zero_pair_conversations:
            print(f"  - {fn}", file=sys.stderr)
        print(f"This is likely caused by a mismatch in '--name {args.name}'.", file=sys.stderr)
        print("!" * 65, file=sys.stderr)

    print("\n" + "=" * 65 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
