import json
import os
from pathlib import Path


def resolve_relationship(
    jid: str,
    map_path: str = "config/relationship_map.json"
) -> tuple[str, str | None]:
    """
    Resolves the relationship class and target Chroma history collection for a WhatsApp JID.

    Args:
        jid: WhatsApp Jabber ID (e.g. '918082667601@s.whatsapp.net', '12345@lid', or '120363@g.us').
        map_path: Path to the contact relationship map JSON file.

    Returns:
        tuple[str, str | None]:
            - ('group', None) for group conversations ending with '@g.us'.
            - (relationship, f"history_{relationship}") for individual contacts.
            - ('unknown', 'history_unknown') as safe fallback for unmapped or malformed JIDs.
    """
    # Safe fallback for None, empty, or non-string JID
    if not jid or not isinstance(jid, str):
        return ("unknown", "history_unknown")

    clean_jid = jid.strip()
    if not clean_jid:
        return ("unknown", "history_unknown")

    # 1. Group check: immediately return ("group", None) without reading map
    if clean_jid.endswith("@g.us"):
        return ("group", None)

    # 2. Strip everything from '@' onward (handles @s.whatsapp.net, @lid, etc.)
    if "@" in clean_jid:
        number = clean_jid.split("@", 1)[0].strip()
    else:
        number = clean_jid

    if not number:
        return ("unknown", "history_unknown")

    # 3. Load relationship map and look up number
    rel_map = {}
    path = Path(map_path)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                rel_map = json.load(f)
        except Exception:
            rel_map = {}

    default_val = rel_map.get("_default", "unknown")
    matched_rel = rel_map.get(number, default_val)
    if not matched_rel:
        matched_rel = "unknown"

    relationship = str(matched_rel).strip().lower()

    # 4. Return tuple (relationship, collection_name)
    if relationship == "group":
        return ("group", None)

    collection_name = f"history_{relationship}"
    return (relationship, collection_name)
