#!/usr/bin/env python3
"""Check Avro schema backwards compatibility.

Compares current .avsc files against the main branch version to ensure:
- No required fields removed
- No type changes on existing fields
- New fields have defaults (backwards compatible)

Usage:
    python scripts/check_schema_compat.py
    # or via Makefile:
    make check-schemas

Exit code 0 = compatible, 1 = breaking changes found.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATHS = [
    "services/pipeline/processor/schema/das_processed_measurement.avsc",
    "services/pipeline/ai_engine/schema/das_detection.avsc",
    "services/pipeline/shared/schema/das_dlq_message.avsc",
    "services/pipeline/shared/schema/string_key.avsc",
]


class SchemaError:
    def __init__(self, schema_path: str, message: str):
        self.schema_path = schema_path
        self.message = message

    def __str__(self):
        return f"  {self.schema_path}: {self.message}"


def get_main_version(schema_path: str) -> dict | None:
    """Get the schema from main branch via git show."""
    try:
        result = subprocess.run(
            ["git", "show", f"main:{schema_path}"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (json.JSONDecodeError, FileNotFoundError):
        return None


def get_current_version(schema_path: str) -> dict | None:
    """Get the current schema from the working tree."""
    full_path = REPO_ROOT / schema_path
    if not full_path.exists():
        return None
    with open(full_path) as f:
        return json.load(f)


def extract_fields(schema: dict) -> dict[str, dict]:
    """Extract field name -> field definition map."""
    fields = {}
    for field in schema.get("fields", []):
        fields[field["name"]] = field
    return fields


def is_required(field: dict) -> bool:
    """A field is required if it has no default and its type is not a union with null."""
    if "default" in field:
        return False
    field_type = field.get("type")
    if isinstance(field_type, list) and "null" in field_type:
        return False
    return True


def check_compatibility(
    schema_path: str, old_schema: dict, new_schema: dict
) -> list[SchemaError]:
    """Check backwards compatibility between old and new schema."""
    errors: list[SchemaError] = []

    old_fields = extract_fields(old_schema)
    new_fields = extract_fields(new_schema)

    # Check for removed fields
    for name, old_field in old_fields.items():
        if name not in new_fields:
            if is_required(old_field):
                errors.append(
                    SchemaError(schema_path, f"required field '{name}' was removed")
                )
            else:
                errors.append(
                    SchemaError(
                        schema_path,
                        f"optional field '{name}' was removed (consumers may still expect it)",
                    )
                )

    # Check for type changes on existing fields
    for name in old_fields:
        if name in new_fields:
            old_type = json.dumps(old_fields[name]["type"], sort_keys=True)
            new_type = json.dumps(new_fields[name]["type"], sort_keys=True)
            if old_type != new_type:
                errors.append(
                    SchemaError(
                        schema_path,
                        f"field '{name}' type changed: {old_type} -> {new_type}",
                    )
                )

    # Check that new fields have defaults
    for name, new_field in new_fields.items():
        if name not in old_fields and is_required(new_field):
            errors.append(
                SchemaError(
                    schema_path,
                    f"new field '{name}' is required (no default). "
                    f"Add a default value for backwards compatibility.",
                )
            )

    # Check nested records recursively
    for name in old_fields:
        if name in new_fields:
            old_type = old_fields[name]["type"]
            new_type = new_fields[name]["type"]
            if isinstance(old_type, dict) and isinstance(new_type, dict):
                if old_type.get("type") == "record" and new_type.get("type") == "record":
                    nested_errors = check_compatibility(
                        f"{schema_path} -> {name}", old_type, new_type
                    )
                    errors.extend(nested_errors)

    return errors


def main():
    all_errors: list[SchemaError] = []
    checked = 0
    skipped = 0

    for schema_path in SCHEMA_PATHS:
        old = get_main_version(schema_path)
        new = get_current_version(schema_path)

        if old is None:
            if new is not None:
                print(f"  NEW: {schema_path} (no main branch version to compare)")
            skipped += 1
            continue

        if new is None:
            all_errors.append(SchemaError(schema_path, "schema file deleted"))
            continue

        if old == new:
            skipped += 1
            continue

        errors = check_compatibility(schema_path, old, new)
        all_errors.extend(errors)
        checked += 1

        if not errors:
            print(f"  OK: {schema_path} (changed, backwards compatible)")

    if all_errors:
        print(f"\nSCHEMA COMPATIBILITY CHECK FAILED ({len(all_errors)} issues):\n")
        for err in all_errors:
            print(err)
        print(
            "\nAvro schemas must be backwards compatible. "
            "Add optional fields with defaults, never remove or rename fields."
        )
        sys.exit(1)
    else:
        print(f"\nSchema compatibility check passed ({checked} changed, {skipped} unchanged)")
        sys.exit(0)


if __name__ == "__main__":
    main()
