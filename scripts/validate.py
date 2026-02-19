#!/usr/bin/env python3
"""
validate.py
-----------
Validates every symbol JSON in processed/ against schemas/symbol.schema.json.
Reports any fields that are missing, wrong type, or violate constraints.

No third-party dependencies — uses stdlib json only.

Usage:
    python scripts/validate.py
    python scripts/validate.py --processed path/to/processed
    python scripts/validate.py --schema   path/to/symbol.schema.json
    python scripts/validate.py --strict   # non-zero exit on any warning
"""

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT    = Path(__file__).resolve().parent.parent
PROCESSED_DIR = REPO_ROOT / "processed"
SCHEMA_PATH   = REPO_ROOT / "schemas" / "symbol.schema.json"

# Lightweight validator (stdlib only — no jsonschema dependency)

REQUIRED_FIELDS = [
    "schema_version", "id", "filename", "display_name",
    "standard", "category", "subcategory",
    "source_path", "svg_path", "metadata_path",
    "svg", "file", "classification", "tags", "snap_points", "notes",
]

CONFIDENCE_VALUES = {"high", "low", "none"}


def _check(errors: list, warnings: list, path: str, condition: bool, message: str) -> None:
    if not condition:
        errors.append(f"  ERROR  {path}: {message}")


def _warn(warnings: list, path: str, message: str) -> None:
    warnings.append(f"  WARN   {path}: {message}")


def validate_symbol(data: dict, json_path: Path) -> tuple[list[str], list[str]]:
    """
    Validate a single symbol metadata dict.
    Returns (errors, warnings) — errors are schema violations, warnings are
    data-quality issues that don't break consumers.
    """
    errors: list[str]   = []
    warnings: list[str] = []
    name = str(json_path)

    # Required fields present
    for field in REQUIRED_FIELDS:
        _check(errors, warnings, name, field in data, f"missing required field '{field}'")

    if not isinstance(data, dict):
        errors.append(f"  ERROR  {name}: root must be an object")
        return errors, warnings

    # schema_version
    sv = data.get("schema_version", "")
    _check(errors, warnings, name, isinstance(sv, str) and re.match(r"^\d+\.\d+\.\d+$", sv),
           f"schema_version '{sv}' must match X.Y.Z")

    # id
    sym_id = data.get("id", "")
    _check(errors, warnings, name, isinstance(sym_id, str) and sym_id.count("/") >= 2,
           f"id '{sym_id}' must have format <standard>/<category>/<stem>")

    # filename
    fn = data.get("filename", "")
    _check(errors, warnings, name, isinstance(fn, str) and fn.endswith(".svg"),
           f"filename '{fn}' must end with .svg")
    _check(errors, warnings, name, isinstance(fn, str) and fn == fn.lower(),
           f"filename '{fn}' must be lowercase")

    # display_name
    dn = data.get("display_name", "")
    _check(errors, warnings, name, isinstance(dn, str) and len(dn) >= 1,
           "display_name must be a non-empty string")

    # category / subcategory
    cat = data.get("category", "")
    sub = data.get("subcategory", "")
    _check(errors, warnings, name, isinstance(cat, str) and len(cat) >= 1,
           "category must be a non-empty string")
    _check(errors, warnings, name, isinstance(sub, str),
           "subcategory must be a string")
    if cat == "unknown":
        _warn(warnings, name, "category is 'unknown' — consider manual classification")

    # svg block
    svg = data.get("svg", {})
    if isinstance(svg, dict):
        ec = svg.get("element_count")
        _check(errors, warnings, name, isinstance(ec, int) and ec >= 0,
               "svg.element_count must be a non-negative integer")
        if isinstance(ec, int) and ec == 0:
            _warn(warnings, name, "svg.element_count is 0 — SVG may be empty or unparseable")
        _check(errors, warnings, name, isinstance(svg.get("has_text"), bool),
               "svg.has_text must be a boolean")
        if svg.get("view_box") is None:
            _warn(warnings, name, "svg.view_box is null — symbol lacks a viewBox attribute")
    else:
        errors.append(f"  ERROR  {name}: svg must be an object")

    # file block
    file_block = data.get("file", {})
    if isinstance(file_block, dict):
        sb = file_block.get("size_bytes")
        _check(errors, warnings, name, isinstance(sb, int) and sb >= 0,
               "file.size_bytes must be a non-negative integer")
    else:
        errors.append(f"  ERROR  {name}: file must be an object")

    # classification block
    clf = data.get("classification", {})
    if isinstance(clf, dict):
        conf = clf.get("confidence", "")
        _check(errors, warnings, name, conf in CONFIDENCE_VALUES,
               f"classification.confidence '{conf}' must be one of {CONFIDENCE_VALUES}")
        _check(errors, warnings, name, isinstance(clf.get("method"), str),
               "classification.method must be a string")
    else:
        errors.append(f"  ERROR  {name}: classification must be an object")

    # tags
    tags = data.get("tags", [])
    _check(errors, warnings, name, isinstance(tags, list),
           "tags must be an array")
    if isinstance(tags, list):
        _check(errors, warnings, name, all(isinstance(t, str) for t in tags),
               "all tags must be strings")
        if len(tags) == 0:
            _warn(warnings, name, "tags is empty — auto-tags may not have run")

    # SVG file on disk
    expected_svg = json_path.with_suffix(".svg")
    if not expected_svg.exists():
        errors.append(f"  ERROR  {name}: companion SVG '{expected_svg.name}' not found on disk")

    return errors, warnings


# Main

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate all symbol JSONs in processed/ against the schema."
    )
    parser.add_argument("--processed", default=None, metavar="DIR",
                        help="processed/ directory (default: <repo>/processed).")
    parser.add_argument("--schema", default=None, metavar="FILE",
                        help="JSON schema file (default: <repo>/schemas/symbol.schema.json).")
    parser.add_argument("--strict", action="store_true",
                        help="Exit with code 1 if any warnings are found.")
    args = parser.parse_args()

    processed_dir = Path(args.processed).resolve() if args.processed else PROCESSED_DIR
    schema_path   = Path(args.schema).resolve()   if args.schema   else SCHEMA_PATH

    if not processed_dir.exists():
        print(f"ERROR: processed directory not found: {processed_dir}")
        sys.exit(1)

    if not schema_path.exists():
        print(f"WARNING: schema file not found: {schema_path} — schema version check skipped.")
        expected_version = None
    else:
        with open(schema_path, encoding="utf-8") as fh:
            _schema = json.load(fh)
        expected_version = None  # reserved for future version enforcement

    json_files = sorted(f for f in processed_dir.rglob("*.json")
                        if f.name != "registry.json")
    total = len(json_files)
    print(f"Validating {total} symbol files in {processed_dir}\n")

    all_errors:   list[str] = []
    all_warnings: list[str] = []
    invalid = 0

    for json_path in json_files:
        try:
            with open(json_path, encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError as exc:
            all_errors.append(f"  ERROR  {json_path}: invalid JSON — {exc}")
            invalid += 1
            continue

        errors, warnings = validate_symbol(data, json_path)
        all_errors.extend(errors)
        all_warnings.extend(warnings)
        if errors:
            invalid += 1

    # Report
    if all_errors:
        print("ERRORS")
        print("-" * 60)
        for e in all_errors:
            print(e)
        print()

    if all_warnings:
        print("WARNINGS")
        print("-" * 60)
        for w in all_warnings:
            print(w)
        print()

    print("=" * 60)
    print(f"  Files checked : {total}")
    print(f"  Invalid       : {invalid}")
    print(f"  Errors        : {len(all_errors)}")
    print(f"  Warnings      : {len(all_warnings)}")
    print("=" * 60)

    if all_errors or (args.strict and all_warnings):
        sys.exit(1)


if __name__ == "__main__":
    main()
