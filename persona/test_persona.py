import argparse
import json
import os
import sys
import time

# Ensure console supports UTF-8 characters like emojis
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env")
from dotenv import load_dotenv
load_dotenv(load_dotenv_path)
load_dotenv()

from google import genai

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

persona_path = os.path.join(os.path.dirname(__file__), "persona.json")
with open(persona_path, "r", encoding="utf-8") as f:
    persona = json.load(f)

# Real incoming messages selected directly from WhatsApp chat exports
DEFAULT_TEST_PROMPTS = [
    # Friends (Mobeen Ahmed, Mohammad Zaheer, Shashwat, Ritik Choudhary)
    ("friends", "Eid mubarak bhai......"),
    ("friends", "Gar pa sab kaise hain"),
    ("friends", "Math ke assignment bheje kya tune madam ko"),
    ("friends", "Pubg khedat aahe ka tu"),

    # Professional (Rohit Meshram Sir NML)
    ("professional", "U send me 2-3 pages daily by 11 PM..."),
    ("professional", "Send me edited paper"),
    ("professional", "When u r coming back?"),

    # Family (Domestic & status checks)
    ("family", "Ghar kab tak aaoge beta?"),
    ("family", "Tabiyat kaisi hai abhi? Dawa le li?"),
]


def generate_reply(relationship: str, incoming_message: str) -> str:
    """Generates an in-character WhatsApp response directly addressing incoming_message."""
    if relationship not in persona["relationships"]:
        return f"[Error: Unknown relationship '{relationship}'. Choose: friends, professional, or family]"

    tone = persona["relationships"][relationship]["tone"]
    examples = persona["relationships"][relationship]["example_replies"]
    hard_rules = "\n".join(f"- {rule}" for rule in persona.get("hard_rules", []))

    prompt = f"""You are texting as: {persona['identity']}

Relationship to sender: {relationship}
Tone to adopt: {tone}

Reference examples of how you text in this relationship (use for tone/cadence reference only, do not blindly copy):
{examples}

Target Hinglish ratio: {persona['hinglish_ratio']}
Target message length: ~{persona['avg_message_length_words']} words
Frequently used emojis: {persona['top_emojis']}

Strict rules:
{hard_rules}

Incoming message from contact:
"{incoming_message}"

CRITICAL INSTRUCTIONS:
- Directly answer or respond to what the incoming message is ACTUALLY saying or asking.
- Do NOT just copy a random greeting or irrelevant example.
- Keep your response in authentic WhatsApp texting style: short, natural, single message.
- If relationship is 'professional': STRICTLY NO EMOJIS, always polite, respectful ('sir').
- If relationship is 'friends': casual, slang ('bhai', 'be', 're'), emojis allowed.
- If relationship is 'family': respectful, caring, reassuring.
- Output ONLY the reply message text (one line, no quotes, no commentary)."""

    # Try models in order of quota availability
    models_to_try = [
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3-flash-preview",
        "gemini-3.5-flash"
    ]

    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            return response.text.strip()
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "503" in err_str:
                continue
            # If unexpected error, try next model
            continue

    return "Ok"


def run_batch_test() -> None:
    print("=" * 65)
    print("RUNNING BATCH PERSONA TESTS")
    print("=" * 65)
    for relationship, incoming in DEFAULT_TEST_PROMPTS:
        reply = generate_reply(relationship, incoming)
        print(f"[{relationship.upper()}] {incoming} -> {reply}", flush=True)
    print("=" * 65)


def run_interactive_mode() -> None:
    print("\n" + "=" * 60)
    print("INTERACTIVE WHATSAPP PERSONA TESTER")
    print("Type 'exit' or 'quit' to stop.")
    print("=" * 60)

    category_map = {"1": "friends", "2": "professional", "3": "family"}

    while True:
        print("\nSelect Relationship:")
        print("  1. friends")
        print("  2. professional")
        print("  3. family")
        choice = input("Enter choice (1/2/3) or name: ").strip().lower()

        if choice in ("exit", "quit", "q"):
            print("Exiting interactive test.")
            break

        relationship = category_map.get(choice, choice)
        if relationship not in persona["relationships"]:
            print(f"Invalid option '{choice}'. Please select 1, 2, or 3.")
            continue

        incoming = input(f"Enter incoming message for [{relationship}]: ").strip()
        if not incoming:
            continue
        if incoming.lower() in ("exit", "quit", "q"):
            break

        reply = generate_reply(relationship, incoming)
        print(f"[{relationship.upper()}] Reply -> {reply}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test WhatsApp Persona Responses")
    parser.add_argument("-i", "--interactive", action="store_true", help="Launch interactive live tester")
    parser.add_argument("-r", "--relationship", choices=["friends", "professional", "family"], help="Relationship category")
    parser.add_argument("-m", "--message", help="Single incoming message to test")
    args = parser.parse_args()

    if args.interactive:
        run_interactive_mode()
    elif args.relationship and args.message:
        reply = generate_reply(args.relationship, args.message)
        print(f"[{args.relationship.upper()}] {args.message} -> {reply}")
    else:
        run_batch_test()


if __name__ == "__main__":
    main()
