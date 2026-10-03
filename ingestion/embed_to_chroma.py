import hashlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import chromadb
from sentence_transformers import SentenceTransformer


def normalize_relationship(raw_rel: str) -> str:
    """Normalize raw relationship string to one of: family, friend, professional, unknown."""
    val = (raw_rel or "").strip().lower()
    if "friend" in val:
        return "friend"
    elif "fam" in val:
        return "family"
    elif "prof" in val:
        return "professional"
    return "unknown"


def main():
    processed_pairs_path = Path("data/processed_pairs.jsonl")
    map_path = Path("config/contact_relationship_map.json")
    chroma_host = "localhost"
    chroma_port = 8000
    model_name = "paraphrase-multilingual-mpnet-base-v2"
    batch_size = 50

    print("==========================================================")
    print("      ChromaDB Embedding & Ingestion Pipeline             ")
    print("==========================================================")

    # 1. Validate files
    if not processed_pairs_path.exists():
        print(f"[!] Error: Dataset not found at {processed_pairs_path}")
        sys.exit(1)

    if not map_path.exists():
        print(f"[!] Error: Relationship map not found at {map_path}")
        print("    Run 'python ingestion/build_relationship_map.py' first.")
        sys.exit(1)

    # 2. Load relationship map
    try:
        with open(map_path, "r", encoding="utf-8") as f:
            rel_map = json.load(f)
    except Exception as e:
        print(f"[!] Failed to parse {map_path}: {e}")
        sys.exit(1)

    default_rel = normalize_relationship(rel_map.get("_default", "unknown"))

    # 3. Read processed pairs
    pairs = []
    with open(processed_pairs_path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                their_msg = (data.get("their_message") or "").strip()
                my_reply = (data.get("my_reply") or "").strip()
                if their_msg and my_reply:
                    pairs.append({
                        "index": line_no,
                        "conversation_id": data.get("conversation_id", "unknown"),
                        "their_message": their_msg,
                        "my_reply": my_reply,
                        "timestamp": data.get("timestamp", "")
                    })
            except json.JSONDecodeError as e:
                print(f"[WARN] Skipping malformed JSON line {line_no}: {e}")

    total_pairs = len(pairs)
    print(f"Total valid pairs loaded from dataset: {total_pairs}")
    if total_pairs == 0:
        print("[!] No pairs to embed. Exiting.")
        sys.exit(0)

    # 4. Connect to ChromaDB
    print(f"\nConnecting to ChromaDB server at http://{chroma_host}:{chroma_port}...")
    try:
        client = chromadb.HttpClient(host=chroma_host, port=chroma_port)
        # Verify connection
        client.heartbeat()
        print("[OK] Connected to ChromaDB server successfully.")
    except Exception as e:
        print(f"[!] ERROR: Failed to connect to ChromaDB at http://{chroma_host}:{chroma_port}: {e}")
        print("[!] Make sure the Chroma server is running (e.g. run 'powershell -File ./scripts/setup_session_2_2.ps1').")
        sys.exit(1)

    # 5. Initialize collections for each relationship class
    collection_names = [
        "history_family",
        "history_friend",
        "history_professional",
        "history_unknown"
    ]
    collections = {}
    for name in collection_names:
        collections[name] = client.get_or_create_collection(name=name)
    print(f"[OK] Initialized {len(collection_names)} Chroma collections: {', '.join(collection_names)}")

    # 6. Load SentenceTransformer model once
    print(f"\nLoading embedding model '{model_name}' (cached locally after first download)...")
    start_load = time.time()
    try:
        model = SentenceTransformer(model_name)
        print(f"[OK] Model loaded in {time.time() - start_load:.1f}s.")
    except Exception as e:
        print(f"[!] Failed to load model '{model_name}': {e}")
        sys.exit(1)

    # 7. Process pairs in batches
    print(f"\nGenerating embeddings and upserting in batches of {batch_size}...")
    counts_per_collection = defaultdict(int)
    start_embed = time.time()

    for i in range(0, total_pairs, batch_size):
        batch = pairs[i:i + batch_size]
        texts = [p["their_message"] for p in batch]

        # Compute embeddings for batch
        embeddings = model.encode(texts, batch_size=len(texts), show_progress_bar=False).tolist()

        # Group items by target collection
        grouped = defaultdict(lambda: {"ids": [], "embeddings": [], "documents": [], "metadatas": []})

        for p, emb in zip(batch, embeddings):
            cid = p["conversation_id"]
            ts = p["timestamp"]
            idx = p["index"]
            raw_class = rel_map.get(cid, default_rel)
            rel_class = normalize_relationship(raw_class)
            target_col = f"history_{rel_class}"

            # Stable ID: deterministic hash so re-running never creates duplicate records
            raw_hash = f"{cid}_{ts}_{idx}".encode("utf-8")
            stable_id = hashlib.sha256(raw_hash).hexdigest()[:20]

            grouped[target_col]["ids"].append(stable_id)
            grouped[target_col]["embeddings"].append(emb)
            grouped[target_col]["documents"].append(p["their_message"])
            grouped[target_col]["metadatas"].append({
                "conversation_id": cid,
                "timestamp": ts,
                "my_reply": p["my_reply"],
                "relationship": rel_class
            })

            counts_per_collection[target_col] += 1

        # Upsert each collection's batch
        for col_name, data in grouped.items():
            if data["ids"]:
                collections[col_name].upsert(
                    ids=data["ids"],
                    embeddings=data["embeddings"],
                    documents=data["documents"],
                    metadatas=data["metadatas"]
                )

        processed = min(i + batch_size, total_pairs)
        pct = (processed / total_pairs) * 100
        print(f"[*] Processed {processed}/{total_pairs} pairs ({pct:.1f}%)...")

    total_time = time.time() - start_embed
    print(f"\n[OK] All {total_pairs} pairs embedded and upserted in {total_time:.1f}s.")

    # 8. Print summary
    print("\n==========================================================")
    print("                 INGESTION SUMMARY                        ")
    print("==========================================================")
    for col_name in collection_names:
        newly_added = counts_per_collection[col_name]
        total_in_db = collections[col_name].count()
        print(f"Collection '{col_name:22}': {newly_added:5} pairs added (total in store: {total_in_db})")

    empty_collections = [c for c in collection_names if counts_per_collection[c] == 0]
    if empty_collections:
        print("\n[WARN] The following collections received 0 pairs in this run:")
        for col in empty_collections:
            print(f"  - {col} (No contacts tagged with this relationship category in config)")
    else:
        print("\n[OK] All collections received embedded pairs!")

    print("==========================================================")


if __name__ == "__main__":
    main()
