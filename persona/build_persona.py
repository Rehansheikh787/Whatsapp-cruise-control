#!/usr/bin/env python3
"""
build_persona.py

Analyzes exported WhatsApp chat logs to extract personal messaging style signals:
- Sample size (total messages sent)
- Hinglish ratio (% of messages containing common Hindi-in-Latin-script words)
- Average message length (in words)
- Top 15 most-used emojis and frequencies
Outputs a human-readable terminal summary and saves results to persona/style_signals.json.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter

# Common Hindi words written in Latin script
HINGLISH_KEYWORDS = [
    "hai", "kya", "nahi", "yaar", "matlab", "acha", "theek", "bhai", "haan", "toh",
    "achha", "thik", "ha", "nahin", "nhi", "bhaiya", "bhaijaan", "bhi", "yeh", "ye",
    "wo", "kaha", "kahaa", "tera", "teri", "tere", "mera", "meri", "mere", "tune",
    "maine", "apko", "hum", "sab", "kar", "kare", "karna", "raha", "rahi", "hoga"
]

HINGLISH_REGEX = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in HINGLISH_KEYWORDS) + r")\b",
    re.IGNORECASE
)

# Regex matching standard WhatsApp message headers:
# e.g., "14/05/21, 9:05 am - Sender Name: Message text"
# Handles variable date/time formats, 12h/24h, and non-breaking spaces
MESSAGE_HEADER_REGEX = re.compile(
    r"^(\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4},\s+\d{1,2}:\d{2}(?::\d{2})?(?:[\s\u202f]?[ap]m)?)\s+-\s+([^:]+?):\s+(.*)$",
    re.IGNORECASE
)

# Regex covering Unicode emoji blocks without requiring external packages
EMOJI_REGEX = re.compile(
    r"[\U0001F600-\U0001F64F"  # Emoticons
    r"\U0001F300-\U0001F5FF"  # Misc Symbols & Pictographs
    r"\U0001F680-\U0001F6FF"  # Transport & Map Symbols
    r"\U0001F700-\U0001F7FF"  # Alchemical & Geometric Shapes Extended
    r"\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
    r"\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
    r"\U0001FA00-\U0001FAFF"  # Symbols and Pictographs Extended-A
    r"\u2600-\u26FF"          # Misc Symbols
    r"\u2700-\u27BF]"         # Dingbats
    r"(?:[\uFE00-\uFE0F])?"   # Optional Variation Selector
    r"(?:[\U0001F3FB-\U0001F3FF])?"  # Optional Skin Tone Modifier
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze WhatsApp export to extract author style signals."
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Path to WhatsApp .txt export file"
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Exact sender name as it appears in the export (e.g. '@Rehan Sheikh')"
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path for output JSON file (defaults to persona/style_signals.json)"
    )
    return parser.parse_args()


def extract_messages(file_path: str, sender_name: str) -> tuple[list[str], set[str]]:
    """
    Reads the export file and extracts messages belonging to sender_name.
    Also returns a set of all unique sender names encountered.
    Handles multiline messages gracefully.
    """
    matched_messages: list[str] = []
    all_senders: set[str] = set()
    current_message: list[str] | None = None

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            match = MESSAGE_HEADER_REGEX.match(line)
            if match:
                # Flush previous message if one was in progress
                if current_message is not None:
                    matched_messages.append("\n".join(current_message).strip())
                    current_message = None

                sender = match.group(2).strip()
                message_content = match.group(3)
                all_senders.add(sender)

                if sender == sender_name:
                    current_message = [message_content]
            else:
                # Continuation line of a multi-line message
                if current_message is not None:
                    current_message.append(line.rstrip("\r\n"))

        if current_message is not None:
            matched_messages.append("\n".join(current_message).strip())

    return matched_messages, all_senders


def compute_style_signals(messages: list[str], sender_name: str, file_path: str) -> dict:
    total_messages = len(messages)
    if total_messages == 0:
        return {}

    # Hinglish calculation
    hinglish_count = 0
    total_words = 0
    emoji_counter: Counter[str] = Counter()

    for msg in messages:
        # Check Hinglish
        if HINGLISH_REGEX.search(msg):
            hinglish_count += 1

        # Message length in words
        words = msg.split()
        total_words += len(words)

        # Extract emojis
        found_emojis = EMOJI_REGEX.findall(msg)
        for em in found_emojis:
            emoji_counter[em] += 1

    hinglish_percentage = round((hinglish_count / total_messages) * 100, 2)
    hinglish_ratio = round(hinglish_count / total_messages, 4)
    avg_message_length = round(total_words / total_messages, 2)

    top_15_emojis = [
        {"emoji": emoji, "count": count}
        for emoji, count in emoji_counter.most_common(15)
    ]

    return {
        "sender_name": sender_name,
        "source_file": file_path,
        "total_sample_size": total_messages,
        "hinglish_messages_count": hinglish_count,
        "hinglish_ratio": hinglish_ratio,
        "hinglish_percentage": hinglish_percentage,
        "average_message_length_words": avg_message_length,
        "top_15_emojis": top_15_emojis,
    }


def print_summary(stats: dict) -> None:
    print("\n" + "=" * 50)
    print(f"STYLE SIGNALS SUMMARY: {stats['sender_name']}")
    print("=" * 50)
    print(f"Source File         : {stats['source_file']}")
    print(f"Total Sample Size   : {stats['total_sample_size']} messages")
    print(f"Hinglish Messages   : {stats['hinglish_messages_count']} ({stats['hinglish_percentage']}%)")
    print(f"Avg Message Length  : {stats['average_message_length_words']} words")
    print("-" * 50)
    print("Top Emojis:")
    if stats["top_15_emojis"]:
        for i, item in enumerate(stats["top_15_emojis"], 1):
            print(f"  {i:>2}. {item['emoji']} : {item['count']}")
    else:
        print("  (None detected)")
    print("=" * 50 + "\n")


def main() -> int:
    # Ensure Windows console supports UTF-8 characters like emojis
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = parse_arguments()

    if not os.path.exists(args.file):
        print(f"ERROR: File not found: {args.file}", file=sys.stderr)
        return 1

    messages, senders = extract_messages(args.file, args.name)

    if not messages:
        print("\n" + "!" * 60, file=sys.stderr)
        print(f"WARNING: Zero matching messages found for sender name '{args.name}'", file=sys.stderr)
        print(f"File checked: {args.file}", file=sys.stderr)
        print("Please double-check the exact sender name as it appears in the raw export.", file=sys.stderr)
        print(f"Unique senders detected in file ({len(senders)} total):", file=sys.stderr)
        for s in sorted(senders):
            print(f"  - '{s}'", file=sys.stderr)
        print("!" * 60 + "\n", file=sys.stderr)
        return 1

    stats = compute_style_signals(messages, args.name, args.file)

    # 1. Print human-readable summary
    print_summary(stats)

    # 2. Write JSON to output path
    output_dir = "persona"
    os.makedirs(output_dir, exist_ok=True)
    if args.output:
        output_path = args.output
        parent = os.path.dirname(output_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
    else:
        output_path = os.path.join(output_dir, "style_signals.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"Saved style signals JSON to: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
