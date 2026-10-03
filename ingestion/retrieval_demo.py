import argparse
import sys
from pathlib import Path

# Ensure repo root is available in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Ensure UTF-8 unbuffered output on Windows console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def log(msg=""):
    """Print with flush=True to ensure real-time terminal output."""
    print(msg, flush=True)


from ingestion.retrieval import client, normalize_collection_name, retrieve_similar

# Built-in sample queries per tone/relationship
DEFAULT_SAMPLE_QUERIES = {
    "family": [
        "Ghar pe sab kaise hai?",
        "Kab tak aayega ghar?",
        "Khana kha liya kya?"
    ],
    "friend": [
        "kaha hai bhai?",
        "aaj sham ko kya scene hai?",
        "match dekhne chalte hai chal"
    ],
    "professional": [
        "Please share the project update by tomorrow morning.",
        "Are you attending the scheduled lab session today?",
        "Please submit the revised report when you finish."
    ],
    "unknown": [
        "Hello, who is this?",
        "Are you available for a quick call?"
    ]
}


def normalize_rel_arg(val: str) -> str:
    """Normalize input relationship argument."""
    v = (val or "").strip().lower()
    if v in ["all", "*"]:
        return "all"
    if "friend" in v:
        return "friend"
    if "fam" in v:
        return "family"
    if "prof" in v:
        return "professional"
    if "unk" in v:
        return "unknown"
    return v


def main():
    parser = argparse.ArgumentParser(
        description="ChromaDB semantic retrieval demo across relationship collections."
    )
    parser.add_argument(
        "--relationship", "-r",
        default="all",
        help="Relationship collection to search: 'all' (default), 'family', 'friend', 'professional', or 'unknown'."
    )
    parser.add_argument(
        "--query", "-q",
        default=None,
        help="Custom incoming message query. If omitted, runs 2-3 built-in realistic sample queries for the target relationship(s)."
    )
    parser.add_argument(
        "--top-k", "-k",
        type=int,
        default=3,
        help="Number of nearest neighbors to retrieve per query (default: 3)."
    )

    args = parser.parse_args()

    selected_rel = normalize_rel_arg(args.relationship)
    all_relationships = ["family", "friend", "professional", "unknown"]

    if selected_rel == "all":
        target_relationships = all_relationships
    elif selected_rel in all_relationships:
        target_relationships = [selected_rel]
    else:
        log(f"[!] Unknown relationship: '{args.relationship}'. Valid options are: all, {', '.join(all_relationships)}")
        sys.exit(1)

    log("==========================================================")
    log("      ChromaDB Semantic Retrieval Demonstration           ")
    log("==========================================================")

    sanity_results = {}

    # Iterate over target relationships
    for rel in target_relationships:
        col_name = normalize_collection_name(rel)
        log(f"\n##########################################################")
        log(f"  TARGET RELATIONSHIP: [{rel.upper()}] -> Collection: {col_name}")
        log(f"##########################################################")

        # Check collection existence and item count
        try:
            collection = client.get_collection(name=col_name)
            doc_count = collection.count()
        except Exception as e:
            err_msg = str(e).lower()
            if "does not exist" in err_msg or "not found" in err_msg:
                doc_count = 0
            else:
                log(f"[!] Error accessing collection {col_name}: {e}")
                sanity_results[rel] = "Error accessing collection"
                continue

        if doc_count == 0:
            log(f"[WARN] ⚠️ no data in {col_name}, skipping (0 pairs indexed)")
            sanity_results[rel] = "Skipped (collection empty)"
            continue

        log(f"[INFO] Collection {col_name} has {doc_count} indexed pairs.")

        # Determine queries to test
        if args.query:
            queries = [args.query]
        else:
            queries = DEFAULT_SAMPLE_QUERIES.get(rel, ["Hello"])

        rel_monotonic_checks = []

        # Run each query using retrieve_similar
        for q_idx, query_text in enumerate(queries, start=1):
            log(f"\n----------------------------------------------------------")
            log(f"  Relationship : {rel.upper()}")
            log(f"  Query [{q_idx}/{len(queries)}]  : \"{query_text}\"")
            log(f"----------------------------------------------------------")

            # Call centralized retrieve_similar
            results = retrieve_similar(
                relationship=rel,
                incoming_message=query_text,
                k=args.top_k
            )

            if not results:
                log("  [No matching results found]")
                continue

            dists = [r["distance"] for r in results]

            # Verify monotonic distance increase
            is_monotonic = True
            for i in range(len(dists) - 1):
                if dists[i] > dists[i + 1]:
                    is_monotonic = False
                    break
            rel_monotonic_checks.append((is_monotonic, dists))

            for rank, item in enumerate(results, start=1):
                dist = item["distance"]
                doc = item["their_message"]
                reply = item["my_reply"]
                contact = item.get("conversation_id", "unknown")
                timestamp = item.get("timestamp", "unknown")

                log(f"  [Result #{rank}]  Distance: {dist:.4f}")
                log(f"    • Matched Message : \"{doc}\"")
                log(f"    • Past My Reply   : \"{reply}\"")
                log(f"    • Context Details : Contact: {contact} | Time: {timestamp}")
                log(f"  - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -")

        # Record sanity check status for relationship
        all_mono = all(check[0] for check in rel_monotonic_checks) if rel_monotonic_checks else True
        dist_preview = ", ".join([f"{d:.4f}" for d in rel_monotonic_checks[0][1]]) if rel_monotonic_checks else "N/A"
        if all_mono:
            sanity_results[rel] = f"Monotonically increasing (sample: [{dist_preview}]) [Expected / Good]"
        else:
            sanity_results[rel] = f"Distance ordering non-monotonic [Needs Attention]"

    # Final Sanity Summary
    log("\n==========================================================")
    log("                 RETRIEVAL SANITY CHECK                   ")
    log("==========================================================")
    for rel, status in sanity_results.items():
        icon = "[OK]" if "Good" in status else ("[WARN]" if "Skipped" in status else "[!]")
        log(f"  {icon} history_{rel:14} : {status}")
    log("==========================================================")


if __name__ == "__main__":
    main()
