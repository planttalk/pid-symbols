"""
export.py
--------------------
Export and migration utilities:
  - export_completed_symbols: copy completed SVG+JSON pairs to an export directory.
  - migrate_to_source_hierarchy: migrate processed/ from 3-part to 4-part layout.
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import paths
from constants import PIP_CATEGORIES, SCHEMA_VERSION
from metadata import processed_dir_for, resolve_stem
from utils import (
    _metadata_quality,
    _rel_or_abs,
    _safe_std_slug,
    _source_slug_from_path,
    _svg_sha256,
)


def export_completed_symbols(source_dir: Path, export_dir: Path, dry_run: bool) -> None:
    """Copy completed symbols (JSON + SVG) from source_dir to export_dir."""
    if not source_dir.is_dir():
        print(f"Error: source directory not found: {source_dir}")
        return

    json_files = sorted(source_dir.rglob("*.json"))
    completed = 0
    copied = 0
    errors = 0
    registry: list[dict] = []

    for json_path in json_files:
        if json_path.name == "registry.json" or "_debug" in json_path.stem:
            continue
        try:
            meta = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            errors += 1
            continue

        if not meta.get("completed", False):
            continue

        svg_path = json_path.with_suffix(".svg")
        if not svg_path.exists():
            errors += 1
            continue

        rel = json_path.relative_to(source_dir)
        target_json = export_dir / rel
        target_svg = target_json.with_suffix(".svg")

        completed += 1
        if not dry_run:
            target_json.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(json_path, target_json)
            shutil.copy2(svg_path, target_svg)
        copied += 1
        registry.append(meta)

    if not dry_run:
        export_dir.mkdir(parents=True, exist_ok=True)
        registry_path = export_dir / "registry.json"
        with open(registry_path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "schema_version": SCHEMA_VERSION,
                    "generated_at":   datetime.now(timezone.utc).isoformat(),
                    "total_symbols":  len(registry),
                    "symbols":        registry,
                },
                fh,
                indent=2,
                ensure_ascii=False,
            )

    print(f"\n{'='*60}")
    print(f"  Completed : {completed}")
    print(f"  Copied    : {copied if not dry_run else 0}")
    print(f"  Errors    : {errors}")
    if dry_run:
        print("  [DRY RUN -- no files written]")
    else:
        print(f"  Output    : {export_dir}")
        print("  Registry  : registry.json")
    print(f"{'='*60}")


def migrate_to_source_hierarchy(processed_dir: Path, dry_run: bool) -> None:
    """Migrate processed/ from 3-part IDs to 4-part source-aware hierarchy.

    For each symbol JSON found in processed_dir:
    1. Reads source_path to determine source_slug via _source_slug_from_path.
    2. Computes new target directory and 4-part ID.
    3. Detects duplicates by content hash; keeps the higher-quality copy.
    4. Moves SVG + JSON to new paths (dry_run = only print, no writes).
    5. Rewrites registry.json with updated entries and hashes map.
    """
    if not processed_dir.is_dir():
        print(f"Error: processed directory not found: {processed_dir}")
        return

    reg_path = processed_dir / "registry.json"
    if not dry_run and reg_path.exists():
        ts  = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        bak = reg_path.with_name(f"registry.{ts}.bak.json")
        shutil.copy2(reg_path, bak)
        print(f"Registry backed up → {bak.name}")

    json_files = sorted(processed_dir.rglob("*.json"))
    moves: list[tuple] = []  # (old_json, new_json, old_svg, new_svg, meta)

    used_stems: dict[Path, set[str]] = {}
    hash_map:   dict[str, dict]      = {}
    hashes:     dict[str, list[str]] = {}

    skipped = 0

    for json_path in json_files:
        if json_path.name == "registry.json" or "_debug" in json_path.stem:
            continue
        try:
            meta = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            print(f"  [SKIP] cannot read {json_path}")
            skipped += 1
            continue

        svg_path = json_path.with_suffix(".svg")
        if not svg_path.exists():
            print(f"  [SKIP] missing SVG for {json_path.name}")
            skipped += 1
            continue

        try:
            content = svg_path.read_text(encoding="utf-8", errors="replace")
            content_hash = _svg_sha256(content)
        except OSError:
            content_hash = ""

        source_path_field = meta.get("source_path", "")
        source_slug       = _source_slug_from_path(source_path_field) if source_path_field else "unknown_source"

        cat      = meta.get("category", "unknown")
        standard = meta.get("standard", "unknown")
        confidence = meta.get("classification", {}).get("confidence", "none")
        method     = meta.get("classification", {}).get("method", "")
        classification = {
            "category":    cat,
            "standard":    standard,
            "subcategory": meta.get("subcategory", ""),
            "confidence":  confidence,
            "method":      method,
        }

        new_target_dir = paths.PROCESSED_DIR / source_slug / (
            "pip" if cat in PIP_CATEGORIES else _safe_std_slug(standard)
        ) / cat

        if new_target_dir not in used_stems:
            used_stems[new_target_dir] = set()

        base_stem  = json_path.stem
        final_stem = base_stem
        if final_stem in used_stems[new_target_dir] or (new_target_dir / (final_stem + ".svg")).exists():
            final_stem = resolve_stem(base_stem, new_target_dir, used_stems[new_target_dir])
        else:
            used_stems[new_target_dir].add(final_stem)

        if cat in PIP_CATEGORIES:
            new_id = f"{source_slug}/pip/{cat}/{final_stem}"
        else:
            new_id = f"{source_slug}/{_safe_std_slug(standard)}/{cat}/{final_stem}"

        new_json = new_target_dir / (final_stem + ".json")
        new_svg  = new_target_dir / (final_stem + ".svg")

        if content_hash and content_hash in hash_map:
            existing_meta = hash_map[content_hash]
            new_quality   = _metadata_quality(meta)
            old_quality   = _metadata_quality(existing_meta)
            if new_quality <= old_quality:
                print(f"  [DUP ] {json_path.name}: duplicate of {existing_meta.get('id')}, skipping")
                hashes.setdefault(content_hash, []).append(new_id)
                skipped += 1
                continue
            else:
                print(f"  [DUP+] {json_path.name}: better quality than {existing_meta.get('id')}, replacing")
                hashes.setdefault(content_hash, []).append(existing_meta.get("id", ""))
                hash_map[content_hash] = meta
        elif content_hash:
            hash_map[content_hash] = meta
            hashes[content_hash]   = [new_id]

        meta["id"]            = new_id
        meta["svg_path"]      = _rel_or_abs(new_svg, paths.REPO_ROOT)
        meta["metadata_path"] = _rel_or_abs(new_json, paths.REPO_ROOT)
        if content_hash:
            meta["content_hash"] = content_hash

        print(
            f"  {'[DRY]' if dry_run else '[MOVE]'} "
            f"{json_path.relative_to(processed_dir)}  →  {new_json.relative_to(processed_dir)}"
        )
        moves.append((json_path, new_json, svg_path, new_svg, meta))

    if dry_run:
        print(f"\n{'='*60}")
        print(f"  Would move : {len(moves)}")
        print(f"  Skipped    : {skipped}")
        print("  [DRY RUN -- no files written]")
        print(f"{'='*60}")
        return

    moved    = 0
    m_errors = 0
    new_registry: list[dict] = []
    for old_json, new_json, old_svg, new_svg, meta in moves:
        try:
            new_json.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old_svg),  str(new_svg))
            shutil.move(str(old_json), str(new_json))
            new_json.write_text(
                json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            new_registry.append(meta)
            moved += 1
        except OSError as exc:
            print(f"  [ERROR] {old_json.name}: {exc}")
            m_errors += 1

    new_reg_path = processed_dir / "registry.json"
    with open(new_reg_path, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "schema_version": SCHEMA_VERSION,
                "generated_at":   datetime.now(timezone.utc).isoformat(),
                "total_symbols":  len(new_registry),
                "symbols":        new_registry,
                "hashes":         hashes,
            },
            fh,
            indent=2,
            ensure_ascii=False,
        )

    print(f"\n{'='*60}")
    print(f"  Moved   : {moved}")
    print(f"  Skipped : {skipped}")
    print(f"  Errors  : {m_errors}")
    print(f"  Registry: {new_reg_path}")
    print(f"{'='*60}")
