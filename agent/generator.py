"""
agent/generator.py

Reply generation module for WhatsApp Cruise Control.
Synthesizes persona, relationship tone, semantic RAG context, and strict behavioral rules
using gemini-3.5-flash via the google-genai SDK.
"""

import json
import logging
import sys
from pathlib import Path

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
from google import genai

from ingestion.retrieval import retrieve_similar

# Load environment variables
load_dotenv(REPO_ROOT / ".env")

logger = logging.getLogger("generator")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Model configuration
MODEL_NAME = "gemini-3.5-flash"
PERSONA_PATH = REPO_ROOT / "persona" / "persona.json"

# Initialize genai client once at module level
client = genai.Client()


def _load_persona() -> dict:
    """Loads and returns the persona definition from persona/persona.json."""
    try:
        with open(PERSONA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to load persona file from %s: %s", PERSONA_PATH, e)
        return {}


def generate_reply(incoming_text: str, relationship: str) -> str:
    """
    Generates an authentic WhatsApp reply matching the user's persona and relationship tone.

    Args:
        incoming_text (str): Incoming message text from the sender.
        relationship (str): Relationship category ('friend', 'family', 'professional', etc.).

    Returns:
        str: Generated reply text, or a safe fallback string if generation fails or is blocked.
    """
    persona = _load_persona()
    rel_normalized = (relationship or "").strip().lower()

    # Match relationship in persona dictionary (handling 'friend' vs 'friends')
    relationships_data = persona.get("relationships", {})
    if rel_normalized in relationships_data:
        rel_info = relationships_data[rel_normalized]
    elif rel_normalized == "friend" and "friends" in relationships_data:
        rel_info = relationships_data["friends"]
    elif rel_normalized == "friends" and "friend" in relationships_data:
        rel_info = relationships_data["friend"]
    else:
        rel_info = {}

    rel_tone = rel_info.get("tone", "Conversational, natural, and polite.")

    # Retrieve similar past turns via ChromaDB RAG
    try:
        retrieved_pairs = retrieve_similar(relationship=relationship, incoming_message=incoming_text, k=3)
    except Exception as e:
        logger.warning(
            "Could not retrieve similar pairs from ChromaDB (%s). Proceeding with persona alone.",
            e,
        )
        retrieved_pairs = []

    # Persona metadata
    identity = persona.get(
        "identity",
        "Rehan Sheikh, engineering student & AI developer. Natural Indian texting cadence across Hindi/Hinglish/English.",
    )
    work_interests = persona.get("work_and_interests", "Software engineering, RAG agents, Python pipelines.")
    hinglish_ratio = persona.get("hinglish_ratio", 0.38)
    avg_words = persona.get("avg_message_length_words", 4.0)
    top_emojis = ", ".join(persona.get("top_emojis", ["😂", "👍", "🙏"]))
    hard_rules = persona.get("hard_rules", [])

    # Format few-shot examples if available
    few_shot_block = ""
    if retrieved_pairs:
        examples = []
        for pair in retrieved_pairs:
            their_msg = pair.get("their_message", "").strip()
            my_rep = pair.get("my_reply", "").strip()
            if their_msg and my_rep:
                examples.append(f'Their message: "{their_msg}"\nMy reply: "{my_rep}"')
        if examples:
            few_shot_block = (
                "\n\nHere are real examples of how I replied to similar messages in past WhatsApp chats with this contact type:\n"
                + "\n---\n".join(examples)
                + "\n---"
            )

    hard_rules_block = ""
    if hard_rules:
        rules_text = "\n".join(f"- {rule}" for rule in hard_rules)
        hard_rules_block = f"\n\nStrict Persona Safety Rules:\n{rules_text}"

    prompt = f"""You are generating an automated WhatsApp reply as myself. You must sound completely authentic and natural according to my personal messaging style and relationship context.

My Identity:
{identity}

My Context & Interests:
{work_interests}

Target Relationship:
{relationship}

Relationship Tone:
{rel_tone}

Style & Cadence Constraints:
- Hinglish mixing ratio: ~{hinglish_ratio:.2f} (naturally blend Hindi / Hinglish and English words when appropriate for this relationship).
- Typical message length: ~{avg_words:.1f} words (concise, punchy messaging bursts typical of mobile chat, not long emails or paragraphs).
- Frequent emojis: {top_emojis} (use sparingly and naturally, matching the tone for this relationship).{hard_rules_block}{few_shot_block}

Incoming Message from sender:
"{incoming_text}"

CRITICAL INSTRUCTIONS:
- Output ONLY the exact text of the reply.
- Do NOT wrap in quotes, do NOT add prefixes like "Reply:", and do NOT include any meta-explanations.
- Stay in character at all times.
"""

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )

        reply_text = response.text if (response and response.text) else ""
        if not reply_text or not reply_text.strip():
            logger.warning("Empty response or blocked by safety filters. Candidate details: %s", getattr(response, "candidates", None))
            return "[no reply generated — check response.candidates for details]"

        return reply_text.strip()

    except Exception as e:
        logger.error("Error invoking %s: %s", MODEL_NAME, e)
        return "[no reply generated — check response.candidates for details]"


if __name__ == "__main__":
    print("==========================================================")
    print("          agent/generator.py (Manual Dry-Run)             ")
    print("==========================================================")

    test_cases = [
        ("friend", "kaha hai bhai? Shaam ko milte hai kya?"),
        ("professional", "Please submit the updated project report by tomorrow morning."),
        ("family", "Beta khana kha liya? Ghar kab tak aayega?"),
    ]

    for rel, msg in test_cases:
        print(f"\n[Relationship] : {rel.upper()}")
        print(f"[Incoming]     : \"{msg}\"")
        reply = generate_reply(incoming_text=msg, relationship=rel)
        print(f"[Generated]    : \"{reply}\"")
        print("-" * 50)
