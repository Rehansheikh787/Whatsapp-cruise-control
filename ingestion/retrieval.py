"""
ingestion/retrieval.py

Exposes semantic retrieval functions over ChromaDB relationship collections.
Loads the SentenceTransformer embedding model and ChromaDB HttpClient once at module level.
"""

import sys
from pathlib import Path

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import chromadb
from sentence_transformers import SentenceTransformer

CHROMA_HOST = "localhost"
CHROMA_PORT = 8000
MODEL_NAME = "paraphrase-multilingual-mpnet-base-v2"

# Module-level instances loaded once on import
client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
model = SentenceTransformer(MODEL_NAME)


def normalize_collection_name(relationship: str) -> str:
    """Normalizes relationship string to Chroma collection name: 'history_<relationship>'."""
    rel = (relationship or "").strip().lower()
    if rel.startswith("history_"):
        return rel
    return f"history_{rel}"


def retrieve_similar(
    relationship: str,
    incoming_message: str,
    k: int = 3
) -> list[dict]:
    """
    Retrieves the top-k most semantically similar past turns for a given relationship.

    Args:
        relationship: Target relationship ('friend', 'professional', 'family', 'unknown').
        incoming_message: Incoming text to match against past received messages.
        k: Maximum number of nearest neighbors to retrieve (default: 3).

    Returns:
        list[dict]: A list of dicts with schema:
            [
                {
                    "their_message": str,
                    "my_reply": str,
                    "distance": float,
                    "conversation_id": str,  # contextual metadata
                    "timestamp": str        # contextual metadata
                },
                ...
            ]
        Returns an empty list [] if collection does not exist, has 0 items, or incoming_message is empty.
        Raises an exception only on genuine ChromaDB/connection failures.
    """
    if not incoming_message or not isinstance(incoming_message, str) or not incoming_message.strip():
        return []

    if k <= 0:
        return []

    col_name = normalize_collection_name(relationship)

    # 1. Check if collection exists
    try:
        collection = client.get_collection(name=col_name)
    except Exception as e:
        # If collection does not exist in Chroma, return empty list safely
        err_msg = str(e).lower()
        if "does not exist" in err_msg or "not found" in err_msg:
            return []
        # Re-raise genuine connection failures
        raise

    # 2. Check if collection has documents
    try:
        count = collection.count()
    except Exception:
        raise

    if count == 0:
        return []

    # 3. Compute embedding and query
    clean_query = incoming_message.strip()
    query_emb = model.encode([clean_query], show_progress_bar=False).tolist()

    n_results = min(k, count)
    res = collection.query(
        query_embeddings=query_emb,
        n_results=n_results,
        include=["documents", "metadatas", "distances"]
    )

    docs = res["documents"][0] if res.get("documents") else []
    metas = res["metadatas"][0] if res.get("metadatas") else []
    dists = res["distances"][0] if res.get("distances") else []

    results: list[dict] = []
    for doc, meta, dist in zip(docs, metas, dists):
        meta = meta or {}
        results.append({
            "their_message": doc or "",
            "my_reply": meta.get("my_reply", ""),
            "distance": float(dist),
            "conversation_id": meta.get("conversation_id", "unknown"),
            "timestamp": meta.get("timestamp", "")
        })

    return results
