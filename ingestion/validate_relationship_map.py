import json
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
    map_path = Path("config/contact_relationship_map.json")

    print("==========================================================")
    print("        Validate Contact Relationship Map                 ")
    print("==========================================================")

    # 1. Check file existence
    if not map_path.exists():
        print(f"[!] FATAL: Relationship map not found at {map_path}")
        print("    Run 'python ingestion/build_relationship_map.py' first.")
        sys.exit(1)

    if not processed_pairs_path.exists():
        print(f"[!] FATAL: Dataset not found at {processed_pairs_path}")
        sys.exit(1)

    # 2. Load relationship map
    try:
        with open(map_path, "r", encoding="utf-8") as f:
            rel_map = json.load(f)
    except Exception as e:
        print(f"[!] FATAL: Failed to parse {map_path}: {e}")
        sys.exit(1)

    # 3. Collect distinct conversation IDs from processed pairs
    conversation_ids = set()
    with open(processed_pairs_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                cid = data.get("conversation_id")
                if cid:
                    conversation_ids.add(cid)
            except json.JSONDecodeError:
                continue

    sorted_ids = sorted(list(conversation_ids))

    missing_ids = []
    unclassified_ids = []
    valid_ids = []

    for cid in sorted_ids:
        if cid not in rel_map:
            missing_ids.append(cid)
        else:
            val = str(rel_map[cid]).strip()
            if val.upper() == "REPLACE_ME" or not val:
                unclassified_ids.append(cid)
            else:
                valid_ids.append((cid, val))

    # 4. Report status
    print(f"Total conversation_ids in dataset : {len(sorted_ids)}")
    print(f"Properly mapped and classified     : {len(valid_ids)}")
    print(f"Missing from map entirely          : {len(missing_ids)}")
    print(f"Still set to 'REPLACE_ME' or empty : {len(unclassified_ids)}")

    has_errors = bool(missing_ids or unclassified_ids)

    if missing_ids:
        print("\n[!] The following conversation_ids are NOT in config/contact_relationship_map.json:")
        for cid in missing_ids:
            print(f"    - {cid}")

    if unclassified_ids:
        print("\n[!] The following conversation_ids are still unclassified ('REPLACE_ME'):")
        for cid in unclassified_ids:
            print(f"    - {cid}")

    if has_errors:
        print("\n==========================================================")
        print("[!] VALIDATION FAILED:")
        print("Please edit config/contact_relationship_map.json to assign real")
        print("relationship tags (e.g. family, friends, professional) before proceeding.")
        print("==========================================================")
        sys.exit(1)
    else:
        print("\nClassifications breakdown:")
        for cid, val in valid_ids:
            print(f"  * {cid:25} -> {val}")
        print("\n==========================================================")
        print("[OK] VALIDATION PASSED: All conversation_ids are classified!")
        print("==========================================================")
        sys.exit(0)


if __name__ == "__main__":
    main()
