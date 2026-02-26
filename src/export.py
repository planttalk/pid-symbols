"""
export.py
--------------------
Export and migration utilities:
  - export_completed_symbols: copy completed SVG+JSON pairs to an export directory.
  - migrate_to_source_hierarchy: migrate processed/ from 3-part to 4-part layout.
  - dedup_input: delete duplicate SVG files from an input directory.
  - migrate_legacy_completed: merge snap_points/notes from old 3-part JSONs into
      the matching 4-part JSONs, matched by content hash.
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from . import paths
from .constants import PIP_CATEGORIES, SCHEMA_VERSION
from .metadata import resolve_stem
from .svg_utils import _minify_svg
from .utils import (
    _metadata_quality,
    _rel_or_abs,
    _safe_std_slug,
    _source_slug_from_path,
    _svg_sha256,
)


def export_completed_symbols(source_dir: Path, export_dir: Path, dry_run: bool) -> None:
    """Copy completed symbols (JSON + SVG) from source_dir to export_dir.

    Only symbols with a 4-part id (origin/standard/category/stem) are exported
    so the output always has a clean origin/standard/category/ folder structure.

    The exported JSON has svg_path and metadata_path rewritten to be relative to
    export_dir so the package is self-contained and not coupled to the original
    processed/ tree.
    """
    if not source_dir.is_dir():
        print(f"Error: source directory not found: {source_dir}")
        return

    json_files = sorted(source_dir.rglob("*.json"))
    completed = 0
    copied = 0
    skipped = 0
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

        # Only export 4-part structure (origin/standard/category/stem)
        sym_id = meta.get("id", "")
        if sym_id.count("/") < 3:
            skipped += 1
            continue

        svg_path = json_path.with_suffix(".svg")
        if not svg_path.exists():
            errors += 1
            continue

        # Destination mirrors the source tree under export_dir
        rel = json_path.relative_to(source_dir)
        target_json = export_dir / rel
        target_svg = target_json.with_suffix(".svg")

        # Rewrite path fields so the exported JSON is self-contained.
        # Paths are stored relative to export_dir (portable, no REPO_ROOT coupling).
        rel_posix = rel.as_posix()
        exported_meta = dict(meta)
        exported_meta["svg_path"] = rel.with_suffix(".svg").as_posix()
        exported_meta["metadata_path"] = rel_posix

        completed += 1
        if not dry_run:
            target_json.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(svg_path, target_svg)
            target_json.write_text(
                json.dumps(exported_meta, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        copied += 1
        registry.append(exported_meta)

    if not dry_run:
        export_dir.mkdir(parents=True, exist_ok=True)
        registry_path = export_dir / "registry.json"
        with open(registry_path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "schema_version": SCHEMA_VERSION,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "total_symbols": len(registry),
                    "symbols": registry,
                },
                fh,
                indent=2,
                ensure_ascii=False,
            )

    print(f"\n{'=' * 60}")
    print(f"  Completed  : {completed}")
    print(f"  Copied     : {copied if not dry_run else 0}")
    if skipped:
        print(f"  Skipped    : {skipped}  (legacy 3-part structure, not exported)")
    print(f"  Errors     : {errors}")
    if dry_run:
        print("  [DRY RUN -- no files written]")
    else:
        print(f"  Output     : {export_dir}")
        print("  Registry   : registry.json")
    print(f"{'=' * 60}")


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
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        bak = reg_path.with_name(f"registry.{ts}.bak.json")
        shutil.copy2(reg_path, bak)
        print(f"Registry backed up → {bak.name}")

    json_files = sorted(processed_dir.rglob("*.json"))
    moves: list[tuple] = []  # (old_json, new_json, old_svg, new_svg, meta)

    used_stems: dict[Path, set[str]] = {}
    hash_map: dict[str, dict] = {}
    hashes: dict[str, list[str]] = {}

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
        source_slug = (
            _source_slug_from_path(source_path_field)
            if source_path_field
            else "unknown_source"
        )

        cat = meta.get("category", "unknown")
        standard = meta.get("standard", "unknown")

        new_target_dir = (
            paths.PROCESSED_DIR
            / source_slug
            / ("pip" if cat in PIP_CATEGORIES else _safe_std_slug(standard))
            / cat
        )

        if new_target_dir not in used_stems:
            used_stems[new_target_dir] = set()

        base_stem = json_path.stem
        final_stem = base_stem
        if final_stem in used_stems[new_target_dir]:
            final_stem = resolve_stem(
                base_stem, new_target_dir, used_stems[new_target_dir]
            )
        else:
            used_stems[new_target_dir].add(final_stem)

        if cat in PIP_CATEGORIES:
            new_id = f"{source_slug}/pip/{cat}/{final_stem}"
        else:
            new_id = f"{source_slug}/{_safe_std_slug(standard)}/{cat}/{final_stem}"

        new_json = new_target_dir / (final_stem + ".json")
        new_svg = new_target_dir / (final_stem + ".svg")

        if content_hash and content_hash in hash_map:
            existing_meta = hash_map[content_hash]
            new_quality = _metadata_quality(meta)
            old_quality = _metadata_quality(existing_meta)
            if new_quality <= old_quality:
                print(
                    f"  [DUP ] {json_path.name}: duplicate of {existing_meta.get('id')}, skipping"
                )
                hashes.setdefault(content_hash, []).append(new_id)
                skipped += 1
                continue
            else:
                print(
                    f"  [DUP+] {json_path.name}: better quality than {existing_meta.get('id')}, replacing"
                )
                hashes.setdefault(content_hash, []).append(existing_meta.get("id", ""))
                hash_map[content_hash] = meta
        elif content_hash:
            hash_map[content_hash] = meta
            hashes[content_hash] = [new_id]

        meta["id"] = new_id
        meta["svg_path"] = _rel_or_abs(new_svg, paths.REPO_ROOT)
        meta["metadata_path"] = _rel_or_abs(new_json, paths.REPO_ROOT)
        if content_hash:
            meta["content_hash"] = content_hash

        print(
            f"  {'[DRY]' if dry_run else '[MOVE]'} "
            f"{json_path.relative_to(processed_dir)}  →  {new_json.relative_to(processed_dir)}"
        )
        moves.append((json_path, new_json, svg_path, new_svg, meta))

    if dry_run:
        print(f"\n{'=' * 60}")
        print(f"  Would move : {len(moves)}")
        print(f"  Skipped    : {skipped}")
        print("  [DRY RUN -- no files written]")
        print(f"{'=' * 60}")
        return

    moved = 0
    m_errors = 0
    new_registry: list[dict] = []
    for old_json, new_json, old_svg, new_svg, meta in moves:
        try:
            new_json.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old_svg), str(new_svg))
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
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "total_symbols": len(new_registry),
                "symbols": new_registry,
                "hashes": hashes,
            },
            fh,
            indent=2,
            ensure_ascii=False,
        )

    print(f"\n{'=' * 60}")
    print(f"  Moved   : {moved}")
    print(f"  Skipped : {skipped}")
    print(f"  Errors  : {m_errors}")
    print(f"  Registry: {new_reg_path}")
    print(f"{'=' * 60}")


def dedup_input(input_dir: Path, dry_run: bool) -> None:
    """Delete duplicate SVG files from input_dir.

    Two SVGs are considered duplicates when their canonical hashes match
    (same structure, ignoring randomly-generated internal IDs and metadata
    timestamps).  Within each duplicate group the file with the shortest
    path is kept; all others are deleted (or listed in dry-run mode).
    """
    if not input_dir.is_dir():
        print(f"Error: input directory not found: {input_dir}")
        return

    svg_files = sorted(input_dir.rglob("*.svg"))
    print(f"Scanning {len(svg_files)} SVG files under {input_dir}\n")

    # hash → list of paths, in the order they are encountered
    groups: dict[str, list[Path]] = {}
    errors = 0

    for svg_path in svg_files:
        if "_debug" in svg_path.stem:
            continue
        try:
            content = svg_path.read_text(encoding="utf-8", errors="replace")
            h = _svg_sha256(_minify_svg(content))
        except OSError:
            print(f"  [ERROR] cannot read {svg_path.relative_to(input_dir)}")
            errors += 1
            continue
        groups.setdefault(h, []).append(svg_path)

    to_delete: list[tuple[Path, Path]] = []  # (kept, deleted)

    for paths_list in groups.values():
        if len(paths_list) < 2:
            continue
        # Keep the file with the shortest relative path (usually the more
        # "canonical" location); fall back to alphabetical order.
        kept = min(paths_list, key=lambda p: (len(p.parts), str(p)))
        for dup in paths_list:
            if dup != kept:
                to_delete.append((kept, dup))

    if not to_delete:
        print("No duplicates found.")
        print(f"{'=' * 60}")
        return

    deleted = 0
    for kept, dup in to_delete:
        rel_kept = kept.relative_to(input_dir)
        rel_dup = dup.relative_to(input_dir)
        print(f"  {'[DRY]' if dry_run else '[DEL ]'} {rel_dup}  (kept: {rel_kept})")
        if not dry_run:
            try:
                dup.unlink()
                deleted += 1
            except OSError as exc:
                print(f"           ERROR: {exc}")
                errors += 1

    print(f"\n{'=' * 60}")
    print(f"  Duplicates found : {len(to_delete)}")
    print(f"  Deleted          : {deleted if not dry_run else 0}")
    if errors:
        print(f"  Errors           : {errors}")
    if dry_run:
        print("  [DRY RUN -- no files deleted]")
    print(f"{'=' * 60}")


def migrate_legacy_completed(processed_dir: Path, dry_run: bool) -> None:
    """Merge completed snap_points from old 3-part JSONs into 4-part JSONs.

    Old layout: processed/{standard}/{category}/{stem}.json  (id has 2 slashes)
    New layout: processed/{source}/{standard}/{category}/{stem}.json  (id has 3 slashes)

    Matching strategy (in order):
      1. Content hash — most reliable; handles renames and deduplication.
      2. source_path + original_filename — fallback when the SVG was altered
         enough to change the hash but the origin path is unambiguous.

    For each matched pair the following fields are merged into the new JSON:
      snap_points, notes, completed, content_hash (from legacy SVG).
    Already-completed new JSONs are not overwritten unless the legacy record
    has more snap_points.
    """
    if not processed_dir.is_dir():
        print(f"Error: processed directory not found: {processed_dir}")
        return

    # Step 1: build lookup maps from all 4-part JSONs
    print("Building new-structure index…")
    hash_to_new: dict[str, Path] = {}  # content_hash → json path
    srckey_to_new: dict[str, Path] = {}  # "source_path|orig_filename" → json path

    for json_path in sorted(processed_dir.rglob("*.json")):
        if json_path.name == "registry.json" or "_debug" in json_path.stem:
            continue
        try:
            meta = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        sym_id = meta.get("id", "")
        if sym_id.count("/") < 3:
            # still old structure – skip
            continue

        # index by stored hash
        stored_hash = meta.get("content_hash", "")
        if stored_hash:
            hash_to_new[stored_hash] = json_path

        # index by source_path + original_filename
        src = meta.get("source_path", "")
        orig = meta.get("original_filename", "")
        if src and orig:
            srckey_to_new[f"{src}|{orig}"] = json_path

    print(
        f"  Indexed {len(hash_to_new)} new-structure symbols by hash, "
        f"{len(srckey_to_new)} by source key.\n"
    )

    # Step 2: find completed old-structure JSONs
    legacy: list[tuple[Path, dict]] = []

    for json_path in sorted(processed_dir.rglob("*.json")):
        if json_path.name == "registry.json" or "_debug" in json_path.stem:
            continue
        try:
            meta = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        if meta.get("id", "").count("/") >= 3:
            continue  # already new structure
        if not meta.get("completed", False):
            continue

        legacy.append((json_path, meta))

    print(f"Found {len(legacy)} completed legacy symbol(s).\n")

    if not legacy:
        print("Nothing to migrate.")
        return

    # Step 3: match and merge
    merged = 0
    skipped = 0
    no_match = 0
    errors = 0

    for old_json, old_meta in legacy:
        old_svg = old_json.with_suffix(".svg")

        # Compute hash of the legacy SVG for matching
        legacy_hash = ""
        if old_svg.exists():
            try:
                content = old_svg.read_text(encoding="utf-8", errors="replace")
                legacy_hash = _svg_sha256(_minify_svg(content))
            except OSError:
                pass

        # Try hash lookup first, then source-key fallback
        new_json = None
        match_method = ""
        if legacy_hash and legacy_hash in hash_to_new:
            new_json = hash_to_new[legacy_hash]
            match_method = "hash"
        else:
            src_key = f"{old_meta.get('source_path', '')}|{old_meta.get('original_filename', '')}"
            if src_key in srckey_to_new:
                new_json = srckey_to_new[src_key]
                match_method = "source_path"

        rel_old = old_json.relative_to(processed_dir)

        if new_json is None:
            print(f"  [MISS] {rel_old}  — no matching new-structure symbol found")
            no_match += 1
            continue

        try:
            new_meta = json.loads(new_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  [ERR ] {rel_old}  — cannot read target {new_json}: {exc}")
            errors += 1
            continue

        old_pts = old_meta.get("snap_points", [])
        new_pts = new_meta.get("snap_points", [])

        # Skip if the new record is already complete with at least as many points
        if new_meta.get("completed") and len(new_pts) >= len(old_pts):
            print(
                f"  [SKIP] {rel_old}  → {new_json.relative_to(processed_dir)}"
                f"  (already complete, {len(new_pts)} pts)"
            )
            skipped += 1
            continue

        rel_new = new_json.relative_to(processed_dir)
        print(
            f"  {'[DRY]' if dry_run else '[MERGE]'} {rel_old}"
            f"  ->  {rel_new}"
            f"  ({match_method}, {len(old_pts)} snap_points)"
        )

        if not dry_run:
            new_meta["snap_points"] = old_pts
            new_meta["completed"] = True
            if old_meta.get("notes"):
                new_meta["notes"] = old_meta["notes"]
            if legacy_hash:
                new_meta["content_hash"] = legacy_hash
            try:
                new_json.write_text(
                    json.dumps(new_meta, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                merged += 1
            except OSError as exc:
                print(f"           ERROR writing {new_json}: {exc}")
                errors += 1
        else:
            merged += 1  # count as "would merge" in dry-run

    print(f"\n{'=' * 60}")
    print(f"  Legacy completed : {len(legacy)}")
    print(f"  {'Would merge' if dry_run else 'Merged'}    : {merged}")
    print(f"  Skipped (done)   : {skipped}")
    print(f"  No match found   : {no_match}")
    if errors:
        print(f"  Errors           : {errors}")
    if dry_run:
        print("  [DRY RUN -- no files written]")
    print(f"{'=' * 60}")
