#!/usr/bin/env python3
"""
Reformat OID arrays in schema.json files from vertical to horizontal layout.
Changes from:
  "oid": [
    1,
    3,
    6,
    ...
  ]
To:
  "oid": [1, 3, 6, ...]
"""

import json
import re
from pathlib import Path


def reformat_oid_arrays(json_str: str) -> str:
    """
    Reformat OID arrays in JSON from vertical to horizontal layout.
    Preserves all other formatting while compacting oid arrays.
    """
    # Pattern to match vertical OID arrays with any amount of whitespace
    # Matches: "oid": [\n  1,\n  3,\n  ...\n  ]
    pattern = r'"oid"\s*:\s*\[\s*\n\s*([\d,\s\n]*?)\s*\n\s*\]'

    def replace_oid(match: re.Match[str]) -> str:
        # Extract the numbers, split, strip whitespace, rejoin on single line
        numbers_str = match.group(1)
        # Split by comma, strip whitespace from each number
        numbers = [n.strip() for n in numbers_str.split(",") if n.strip()]
        # Rejoin as compact array on single line
        return f'"oid": [{", ".join(numbers)}]'

    return re.sub(pattern, replace_oid, json_str)


def process_schema_file(filepath: str) -> tuple[bool, str]:
    """
    Process a single schema.json file.
    Returns: (success: bool, message: str)
    """
    try:
        # Read the file
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # Reformat OID arrays
        reformatted = reformat_oid_arrays(content)

        # Validate JSON structure is still valid
        try:
            json.loads(reformatted)
        except json.JSONDecodeError as e:
            return False, f"JSON validation failed: {e}"

        # Write back if changed
        if reformatted != content:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(reformatted)
            return True, f"Reformatted: {filepath}"
        else:
            return True, "Already formatted: " + filepath

    except Exception as e:
        return False, f"Error processing {filepath}: {e}"


def main() -> None:
    """Find and reformat all schema.json files in agent-model/"""
    workspace_root = Path(__file__).parent
    agent_model_dir = workspace_root / "agent-model"

    if not agent_model_dir.exists():
        print(f"ERROR: agent-model directory not found at {agent_model_dir}")
        return

    # Find all schema.json files
    schema_files = list(agent_model_dir.glob("*/schema.json"))

    if not schema_files:
        print(f"No schema.json files found in {agent_model_dir}")
        return

    print(f"Found {len(schema_files)} schema.json file(s):\n")

    success_count = 0
    failed_count = 0

    for schema_file in sorted(schema_files):
        success, message = process_schema_file(str(schema_file))
        print(f"  {'✓' if success else '✗'} {message}")
        if success:
            success_count += 1
        else:
            failed_count += 1

    print("\n--- Summary ---")
    print(f"Processed: {len(schema_files)}")
    print(f"Success: {success_count}")
    print(f"Failed: {failed_count}")


if __name__ == "__main__":
    main()
