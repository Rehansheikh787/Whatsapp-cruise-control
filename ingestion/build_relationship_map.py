import json
import os
import sys
from pathlib import Path

# Safe stdout for Windows console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def main():
    processed_pairs_path = Path("data/processed_pairs.jsonl")
    config_dir = Path("config")
    map_path = config_dir / "contact_relationship_map.json"

    # Step 1: Ensure input dataset exists
    if not processed_pairs_path.exists():
        print(f"[!] Error: {processed_pairs_path} does not exist.")
        sys.exit(1)

    # Collect distinct conversation IDs
    conversation_ids = set()
    with open(processed_pairs_path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                cid = data.get("conversation_id")
                if cid:
                    conversation_ids.add(cid)
            except json.JSONDecodeError as e:
                print(f"[WARN] Skipping invalid JSON at line {line_no}: {e}")

    sorted_ids = sorted(list(conversation_ids))

    # Step 2: Load existing map if present, preserving manual classifications
    config_dir.mkdir(parents=True, exist_ok=True)
    existing_map = {}
    if map_path.exists():
        try:
            with open(map_path, "r", encoding="utf-8") as f:
                existing_map = json.load(f)
        except Exception as e:
            print(f"[WARN] Failed to read existing {map_path} ({e}). Starting fresh.")
            existing_map = {}

    # Step 3 & 4: Add new conversation_ids with "REPLACE_ME" & ensure "_default": "unknown"
    updated_map = dict(existing_map)
    if "_default" not in updated_map:
        updated_map["_default"] = "unknown"

    new_ids = []
    for cid in sorted_ids:
        if cid not in updated_map:
            updated_map[cid] = "REPLACE_ME"
            new_ids.append(cid)

    # Step 5: Write back sorted alphabetically by key with 2-space indentation
    sorted_map = dict(sorted(updated_map.items()))
    with open(map_path, "w", encoding="utf-8") as f:
        json.dump(sorted_map, f, indent=2, ensure_ascii=False)

    # Step 6: Print clear summary and highlight pending items
    unclassified = [
        k for k, v in sorted_map.items()
        if k != "_default" and v == "REPLACE_ME"
    ]

    print("==========================================================")
    print("        Contact Relationship Map Builder Summary          ")
    print("==========================================================")
    print(f"Map File Location       : {map_path}")
    print(f"Total conversation_ids  : {len(sorted_ids)}")
    print(f"Newly added in this run : {len(new_ids)}")
    print(f"Pending 'REPLACE_ME'    : {len(unclassified)}")

    if new_ids:
        print("\nNew IDs added to map (set to 'REPLACE_ME'):")
        for cid in new_ids:
            print(f"  + {cid}")

    if unclassified:
        print("\n[ACTION REQUIRED] The following contacts need classification in config/contact_relationship_map.json:")
        for cid in unclassified:
            print(f"  - \"{cid}\": \"REPLACE_ME\"  -> change to family | friends | professional")
    else:
        print("\n[OK] All conversation_ids are classified! None are set to 'REPLACE_ME'.")

    print("==========================================================")


if __name__ == "__main__":
    main()
