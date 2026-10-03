#!/usr/bin/env python3
"""
validate_pairs.py

Validates data/processed_pairs.jsonl with a comprehensive check suite:
1. Total pair count and per-conversation_id breakdown (flags 0 pairs in red).
2. Prints 5 randomly sampled pairs formatted readably.
3. Scans for leaked noise ("omitted", "<Media", "deleted", or empty strings).
4. Flags suspiciously long replies (>100 words).
5. Flags identical or near-identical pairs.
6. Prints a final one-line summary: "✅ Looks good" or "⚠️ N issues found — review above".
"""

import json
import os
import random
import sys
from collections import Counter
from pathlib import Path

# ANSI color codes for terminal formatting
COLOR_RED = "\033[91m"
COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_CYAN = "\033[96m"
COLOR_BOLD = "\033[1m"
COLOR_RESET = "\033[0m"


def normalize_text(text: str) -> str:
    """Strips whitespace and non-alphanumeric characters for near-identical check."""
    return "".join(ch.lower() for ch in text if ch.isalnum())


def main() -> int:
    # Ensure Windows console supports UTF-8 characters and emojis
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    file_path = Path("data/processed_pairs.jsonl")
    raw_export_dir = Path("data/raw_export")

    print("\n" + "=" * 65)
    print(f"{COLOR_BOLD}VALIDATING PROCESSED PAIRS: {file_path}{COLOR_RESET}")
    print("=" * 65 + "\n")

    if not file_path.exists():
        print(f"{COLOR_RED}ERROR: File not found: {file_path}{COLOR_RESET}", file=sys.stderr)
        print("Please run ingestion/parse_export.py first.")
        return 1

    pairs: list[dict] = []
    line_errors: int = 0

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for idx, line in enumerate(f, 1):
            line_str = line.strip()
            if not line_str:
                continue
            try:
                data = json.loads(line_str)
                data["_line_number"] = idx
                pairs.append(data)
            except json.JSONDecodeError as e:
                line_errors += 1
                print(f"{COLOR_RED}[Line {idx}] JSON Decode Error: {e}{COLOR_RESET}")

    total_pairs = len(pairs)
    total_issues = line_errors

    # -------------------------------------------------------------
    # Check 1: Total pair count + per-conversation_id breakdown
    # -------------------------------------------------------------
    print(f"{COLOR_BOLD}[CHECK 1] Pair Counts & Conversation Breakdown{COLOR_RESET}")
    conv_counts = Counter(p.get("conversation_id", "unknown") for p in pairs)

    # Detect any raw export files that yielded 0 pairs
    expected_conv_ids = set()
    if raw_export_dir.exists():
        for rf in raw_export_dir.glob("*.txt"):
            stem = rf.name
            if stem.lower().endswith(".txt"):
                stem = stem[:-4]
            prefix = "WhatsApp Chat with "
            if stem.startswith(prefix):
                stem = stem[len(prefix):]
            slug = "".join(c.lower() if c.isalnum() or c in ("-", "_") else "-" for c in stem).strip("-")
            expected_conv_ids.add(slug)

    print(f"Total Pairs Kept Across All Files: {COLOR_CYAN}{total_pairs}{COLOR_RESET}")
    print(f"{'Conversation ID':<30} | {'Pair Count':<12}")
    print("-" * 45)

    all_convs = sorted(set(list(conv_counts.keys()) + list(expected_conv_ids)))
    for cid in all_convs:
        count = conv_counts.get(cid, 0)
        if count == 0:
            total_issues += 1
            print(f"{COLOR_RED}{cid:<30} | {count:<12} [WARNING: 0 pairs]{COLOR_RESET}")
        else:
            print(f"{cid:<30} | {count:<12}")
    print("-" * 45 + "\n")

    # -------------------------------------------------------------
    # Check 2: 5 Random Sampled Pairs
    # -------------------------------------------------------------
    print(f"{COLOR_BOLD}[CHECK 2] Random Sample of 5 Pairs (Conversational Quality){COLOR_RESET}")
    sample_size = min(5, total_pairs)
    if sample_size > 0:
        sampled_pairs = random.sample(pairs, sample_size)
        for i, sample in enumerate(sampled_pairs, 1):
            conv = sample.get("conversation_id", "unknown")
            ts = sample.get("timestamp", "N/A")
            their = sample.get("their_message", "").replace("\n", "\n    ")
            my = sample.get("my_reply", "").replace("\n", "\n    ")

            print(f"\n--- Sample {i}/{sample_size} [conv: {COLOR_CYAN}{conv}{COLOR_RESET}] (Time: {ts}) ---")
            print(f"{COLOR_YELLOW}THEIR:{COLOR_RESET} {their}")
            print(f"{COLOR_GREEN}MY   :{COLOR_RESET} {my}")
    else:
        print("No pairs available to sample.")
    print("\n" + "-" * 65 + "\n")

    # -------------------------------------------------------------
    # Check 3: Scan for Leaked Noise
    # -------------------------------------------------------------
    print(f"{COLOR_BOLD}[CHECK 3] Scanning for Leaked System/Media Noise{COLOR_RESET}")
    noise_patterns = ["omitted", "<media", "deleted"]
    noise_issues: list[dict] = []

    for p in pairs:
        their = p.get("their_message", "")
        my = p.get("my_reply", "")
        line_num = p.get("_line_number", 0)

        # Check empty string
        if not their.strip() or not my.strip():
            noise_issues.append({
                "line": line_num,
                "reason": "Empty message field detected",
                "their": their,
                "my": my
            })
            continue

        # Check noise patterns (case-insensitive)
        for term in noise_patterns:
            if term.lower() in their.lower():
                noise_issues.append({
                    "line": line_num,
                    "reason": f"Noise '{term}' found in their_message",
                    "their": their,
                    "my": my
                })
                break
            if term.lower() in my.lower():
                noise_issues.append({
                    "line": line_num,
                    "reason": f"Noise '{term}' found in my_reply",
                    "their": their,
                    "my": my
                })
                break

    if noise_issues:
        total_issues += len(noise_issues)
        print(f"{COLOR_YELLOW}Flagged {len(noise_issues)} pair(s) containing noise patterns or empty strings:{COLOR_RESET}")
        for issue in noise_issues[:5]:
            print(f"  • Line {issue['line']}: {issue['reason']}")
            their_snippet = issue['their'].replace('\n', ' ')[:70]
            my_snippet = issue['my'].replace('\n', ' ')[:70]
            print(f"    THEIR: \"{their_snippet}...\"")
            print(f"    MY   : \"{my_snippet}...\"")
        if len(noise_issues) > 5:
            print(f"  ...and {len(noise_issues) - 5} more.")
    else:
        print(f"{COLOR_GREEN}Clean! Zero leaked noise patterns ('omitted', '<Media', 'deleted') or empty strings detected.{COLOR_RESET}")
    print("\n" + "-" * 65 + "\n")

    # -------------------------------------------------------------
    # Check 4: Suspiciously Long Replies (>100 words)
    # -------------------------------------------------------------
    print(f"{COLOR_BOLD}[CHECK 4] Scanning for Suspiciously Long Replies (>100 words){COLOR_RESET}")
    long_reply_issues: list[dict] = []

    for p in pairs:
        my = p.get("my_reply", "")
        words = my.split()
        if len(words) > 100:
            long_reply_issues.append({
                "line": p.get("_line_number", 0),
                "word_count": len(words),
                "conv": p.get("conversation_id", ""),
                "preview": my.replace("\n", " ")[:90]
            })

    if long_reply_issues:
        total_issues += len(long_reply_issues)
        print(f"{COLOR_YELLOW}Flagged {len(long_reply_issues)} pair(s) where my_reply > 100 words:{COLOR_RESET}")
        for item in long_reply_issues[:5]:
            print(f"  • Line {item['line']} [{item['conv']}]: {item['word_count']} words -> \"{item['preview']}...\"")
        if len(long_reply_issues) > 5:
            print(f"  ...and {len(long_reply_issues) - 5} more.")
    else:
        print(f"{COLOR_GREEN}Clean! All replies are within natural conversational lengths (<= 100 words).{COLOR_RESET}")
    print("\n" + "-" * 65 + "\n")

    # -------------------------------------------------------------
    # Check 5: Identical or Near-Identical Messages
    # -------------------------------------------------------------
    print(f"{COLOR_BOLD}[CHECK 5] Scanning for Identical or Near-Identical Pairs{COLOR_RESET}")
    duplicate_issues: list[dict] = []

    for p in pairs:
        their = p.get("their_message", "").strip()
        my = p.get("my_reply", "").strip()

        norm_their = normalize_text(their)
        norm_my = normalize_text(my)

        if norm_their and norm_their == norm_my:
            duplicate_issues.append({
                "line": p.get("_line_number", 0),
                "conv": p.get("conversation_id", ""),
                "their": their.replace("\n", " "),
                "my": my.replace("\n", " ")
            })

    if duplicate_issues:
        total_issues += len(duplicate_issues)
        print(f"{COLOR_YELLOW}Flagged {len(duplicate_issues)} pair(s) with identical/near-identical messages:{COLOR_RESET}")
        for item in duplicate_issues[:5]:
            print(f"  • Line {item['line']} [{item['conv']}]:")
            print(f"    THEIR: \"{item['their']}\"")
            print(f"    MY   : \"{item['my']}\"")
        if len(duplicate_issues) > 5:
            print(f"  ...and {len(duplicate_issues) - 5} more.")
    else:
        print(f"{COLOR_GREEN}Clean! Zero identical or near-identical pairs detected.{COLOR_RESET}")
    print("\n" + "=" * 65 + "\n")

    # -------------------------------------------------------------
    # Check 6: Final Summary
    # -------------------------------------------------------------
    if total_issues == 0:
        print(f"{COLOR_BOLD}{COLOR_GREEN}✅ Looks good{COLOR_RESET}\n")
        return 0
    else:
        print(f"{COLOR_BOLD}{COLOR_YELLOW}⚠️ {total_issues} issues found — review above{COLOR_RESET}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
