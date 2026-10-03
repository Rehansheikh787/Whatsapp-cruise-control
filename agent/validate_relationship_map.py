import argparse
import json
import re
import sys
from pathlib import Path

# Safe stdout for Windows console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

VALID_RELATIONSHIPS = {"family", "friend", "professional", "unknown"}


def validate_relationship_map(map_path: Path | str = "config/relationship_map.json") -> bool:
    """
    Validates config/relationship_map.json against key formatting rules:
      1. All contact keys (except '_default') must be pure digits without '+', spaces, dashes, or letters.
      2. Digit length must be plausible for E.164 phone numbers (8-15 digits).
      3. '_default' must exist and be one of: family, friend, professional, unknown.

    Returns:
        bool: True if validation passed, False otherwise.
    """
    path = Path(map_path)

    print("==========================================================")
    print(f"      Validate Relationship Map ({path})")
    print("==========================================================")

    if not path.exists():
        print(f"[!] FATAL: Map file not found at {path}")
        return False

    try:
        with open(path, "r", encoding="utf-8") as f:
            rel_map = json.load(f)
    except Exception as e:
        print(f"[!] FATAL: Failed to parse {path}: {e}")
        return False

    issues = []
    warnings = []

    # 1. Check "_default" key existence and validity
    if "_default" not in rel_map:
        issues.append("Missing required key '_default' in relationship map.")
    else:
        default_val = str(rel_map["_default"]).strip().lower()
        if default_val not in VALID_RELATIONSHIPS:
            issues.append(
                f"'_default' has invalid value '{rel_map['_default']}'. "
                f"Must be one of: {', '.join(sorted(VALID_RELATIONSHIPS))}."
            )

    # 2. Check all other keys
    contact_keys = [k for k in rel_map.keys() if k != "_default"]
    print(f"Total contacts to validate: {len(contact_keys)}")

    for key in contact_keys:
        val = str(rel_map[key]).strip().lower()

        # Check 1: Flag '+', spaces, dashes, or letters
        invalid_chars = []
        if "+" in key:
            invalid_chars.append("'+'")
        if " " in key:
            invalid_chars.append("spaces")
        if "-" in key:
            invalid_chars.append("dashes")
        if re.search(r"[a-zA-Z]", key):
            invalid_chars.append("letters")

        if invalid_chars or not key.isdigit():
            reasons = ", ".join(invalid_chars) if invalid_chars else "non-digit characters"
            issues.append(
                f"Invalid key '{key}': contains {reasons}. "
                f"Expected raw digits only (e.g. '919876543210' without '+' or spaces)."
            )

        # Check 2: Flag implausible length (fewer than 8 or more than 15 digits)
        digits_only = re.sub(r"\D", "", key)
        if len(digits_only) < 8 or len(digits_only) > 15:
            issues.append(
                f"Implausible digit length for '{key}' ({len(digits_only)} digits). "
                f"Valid E.164 phone numbers must be between 8 and 15 digits."
            )

        # Value validity check (warn if unexpected relationship tag)
        if val not in VALID_RELATIONSHIPS:
            warnings.append(
                f"Contact '{key}' has non-standard relationship tag '{rel_map[key]}'. "
                f"Expected one of: {', '.join(sorted(VALID_RELATIONSHIPS))}."
            )

    # 3. Print Summary Report
    print("\n----------------------------------------------------------")
    if warnings:
        print("[!] Warnings:")
        for w in warnings:
            print(f"  * {w}")
        print("----------------------------------------------------------")

    if issues:
        print("[!] Issues Found:")
        for idx, issue in enumerate(issues, start=1):
            print(f"  {idx}. {issue}")
        print("\n==========================================================")
        print("❌ VALIDATION FAILED: Please fix the issues above.")
        print("==========================================================")
        return False
    else:
        print("[OK] All contact keys are valid raw phone numbers (8-15 digits).")
        print(f"[OK] '_default' is set to '{rel_map.get('_default')}'.")
        print("\nValidated Contacts:")
        for k in contact_keys:
            print(f"  • {k:16} -> {rel_map[k]}")
        print("\n==========================================================")
        print("✅ VALIDATION PASSED: relationship_map.json is clean!")
        print("==========================================================")
        return True


def main():
    parser = argparse.ArgumentParser(
        description="Pre-flight validation for config/relationship_map.json."
    )
    parser.add_argument(
        "--path", "-p",
        default="config/relationship_map.json",
        help="Path to relationship map JSON file (default: config/relationship_map.json)."
    )
    args = parser.parse_args()

    is_valid = validate_relationship_map(args.path)
    sys.exit(0 if is_valid else 1)


if __name__ == "__main__":
    main()
