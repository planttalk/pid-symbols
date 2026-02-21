"""
main.py
--------------------
CLI entry point for the P&ID symbol library pipeline.

Recursively scans input/ for SVG files, classifies each one,
and writes to processed/ (mirrored by source/standard/category):
  - processed/<source>/<standard>/<category>/<normalized_stem>.svg
  - processed/<source>/<standard>/<category>/<normalized_stem>.json
  - processed/registry.json

Usage:
    python main.py
    python main.py --dry-run
    python main.py --augment --augment-count 5 --augment-min-size 256
    python main.py --augment-source processed --augment-count 5 --augment-min-size 256
    python main.py --augment-source completed --augment-count 5 --augment-min-size 256
    python main.py --export-completed ./exported
    python main.py --export-completed ./exported --export-source ./processed
    python main.py --migrate --dry-run
    python main.py --migrate
    python main.py --export-yolo ./yolo-out --augment-count 3 --compose-count 20
    python main.py --dedup-input --dry-run
    python main.py --dedup-input
    python main.py --migrate-legacy-completed --dry-run
    python main.py --migrate-legacy-completed
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import src.paths as paths
from src.augmentation import augment_svgs, export_yolo_datasets
from src.classifier import classify
from src.constants import SCHEMA_VERSION
from src.export import (
    dedup_input,
    export_completed_symbols,
    migrate_legacy_completed,
    migrate_to_source_hierarchy,
)
from src.metadata import build_metadata, processed_dir_for, resolve_stem
from src.svg_utils import _minify_svg
from src.utils import _metadata_quality, _slugify, _svg_sha256


def _prompt_choice(label: str, options: list[str]) -> str | None:
    """Print a numbered menu and return the chosen value, or None for 'All'."""
    print(f"\n{label}:")
    print("  [0] All")
    for i, opt in enumerate(options, 1):
        print(f"  [{i}] {opt}")
    while True:
        raw = input("  > ").strip()
        if raw in ("0", ""):
            return None
        try:
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1]
        except ValueError:
            pass
        print(f"  Please enter a number between 0 and {len(options)}.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Classify input/ SVGs and write processed/ with normalized names."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse and classify without writing any files."
    )
    parser.add_argument(
        "--input", default=None, metavar="DIR",
        help="Input directory to scan for SVGs (default: <repo>/input)."
    )
    parser.add_argument(
        "--output", default=None, metavar="DIR",
        help=(
            "Output directory for processed files "
            "(default: <repo>/processed, or <input>-augmented when using --input/--augment-source/--augment)."
        )
    )
    parser.add_argument(
        "--augment", action="store_true",
        help="Generate augmented PNGs instead of processed SVG/JSON."
    )
    parser.add_argument(
        "--augment-count", type=int, default=5, metavar="N",
        help="Number of augmented PNGs to generate per SVG (default: 5)."
    )
    parser.add_argument(
        "--augment-min-size", type=int, default=256, metavar="PX",
        help="Minimum short-side size in pixels for augmented PNGs (default: 256)."
    )
    parser.add_argument(
        "--augment-source", choices=["completed", "processed"], default=None,
        help="Use completed/ or processed/ as the input source."
    )
    parser.add_argument(
        "--export-completed", default=None, metavar="DIR",
        help="Export completed symbols (copy SVG+JSON) to DIR."
    )
    parser.add_argument(
        "--export-source", default=None, metavar="DIR",
        help="Source symbols root for export (default: <repo>/processed)."
    )
    parser.add_argument(
        "--migrate", action="store_true",
        help="Migrate processed/ to source-aware 4-part folder hierarchy."
    )
    parser.add_argument(
        "--export-yolo", default=None, metavar="DIR",
        help="Export YOLO datasets (one per standard) to DIR."
    )
    parser.add_argument(
        "--compose-count", type=int, default=20, metavar="N",
        help="Multi-symbol composite images per standard group (default: 20). 0 disables.",
    )
    parser.add_argument(
        "--dedup-input", action="store_true",
        help="Delete duplicate SVG files from the input directory (use --dry-run to preview)."
    )
    parser.add_argument(
        "--migrate-legacy-completed", action="store_true",
        help=(
            "Find completed symbols in old 3-part processed/ layout and merge their "
            "snap_points into the matching 4-part symbol, matched by content hash. "
            "Use --dry-run to preview without writing."
        ),
    )
    args = parser.parse_args()

    # Override module-level path globals when CLI args are provided
    if args.input:
        paths.INPUT_DIR = Path(args.input).resolve()
    if args.augment_source and not args.input:
        paths.INPUT_DIR = (paths.REPO_ROOT / args.augment_source).resolve()
    if args.output:
        paths.PROCESSED_DIR = Path(args.output).resolve()
    elif args.input or args.augment_source or args.augment:
        paths.PROCESSED_DIR = paths.INPUT_DIR.parent / f"{paths.INPUT_DIR.name}-augmented"

    if args.export_completed:
        export_dir = Path(args.export_completed).resolve()
        source_dir = (Path(args.export_source).resolve()
                      if args.export_source else paths.PROCESSED_DIR)
        export_completed_symbols(source_dir, export_dir, args.dry_run)
        return

    if args.migrate:
        migrate_to_source_hierarchy(paths.PROCESSED_DIR, args.dry_run)
        return

    if args.dedup_input:
        dedup_input(paths.INPUT_DIR, args.dry_run)
        return

    if args.migrate_legacy_completed:
        migrate_legacy_completed(paths.PROCESSED_DIR, args.dry_run)
        return

    if args.export_yolo:
        yolo_out      = Path(args.export_yolo).resolve()
        registry_path = paths.PROCESSED_DIR / "registry.json"

        # Prompt user to narrow down origin and standard
        sel_origin   = None
        sel_standard = None
        try:
            reg      = json.loads(registry_path.read_text(encoding="utf-8"))
            syms     = reg.get("symbols", [])
            origins  = sorted({s.get("id", "").split("/")[0]
                                for s in syms if s.get("id", "").count("/") >= 3})
            stds     = sorted({s.get("standard", "")
                                for s in syms
                                if s.get("standard", "").lower() not in ("", "unknown")})
            sel_origin   = _prompt_choice("Select origin", origins)
            sel_standard = _prompt_choice("Select standard", stds)
        except (json.JSONDecodeError, OSError):
            print("Warning: could not load registry for filtering — exporting all.")
        except KeyboardInterrupt:
            print("\nAborted.")
            return

        export_yolo_datasets(
            registry_path, yolo_out,
            args.augment_count, args.dry_run, args.augment_min_size,
            origin=sel_origin, standard=sel_standard,
            compose_count=args.compose_count,
        )
        return

    augment_mode = bool(args.augment or args.augment_source)
    if augment_mode:
        if args.augment_count < 1:
            print("Error: --augment-count must be >= 1")
            return
        if args.augment_min_size < 1:
            print("Error: --augment-min-size must be >= 1")
            return
        augment_svgs(paths.INPUT_DIR, paths.PROCESSED_DIR, args.augment_count, args.dry_run, args.augment_min_size)
        return

    generated_at = datetime.now(timezone.utc).isoformat()

    svg_files = sorted(paths.INPUT_DIR.rglob("*.svg"))
    total = len(svg_files)
    print(f"Found {total} SVG files under {paths.INPUT_DIR}\n")

    registry: list[dict]        = []
    processed_count             = 0
    errors                      = 0
    conf_counts: dict[str, int] = {}

    used_stems: dict[Path, set[str]] = {}
    hash_map: dict[str, str]         = {}
    hashes: dict[str, list[str]]     = {}
    duplicates = 0

    for svg_path in svg_files:
        if "_debug" in svg_path.stem:
            continue
        rel = svg_path.relative_to(paths.REPO_ROOT)
        src_rel = str(rel).replace("\\", "/")
        try:
            classification = classify(svg_path)
            target_dir     = processed_dir_for(classification, src_rel)

            if target_dir not in used_stems:
                used_stems[target_dir] = set()

            from src.metadata import _normalize_stem
            base_stem  = _normalize_stem(svg_path.stem, classification["standard"])
            final_stem = resolve_stem(base_stem, target_dir, used_stems[target_dir])
            meta       = build_metadata(svg_path, final_stem, classification, src_rel)
        except Exception as exc:
            print(f"  [ERROR] {rel}: {exc}")
            errors += 1
            continue

        raw_svg      = svg_path.read_text(encoding="utf-8", errors="replace")
        minified     = _minify_svg(raw_svg)
        content_hash = _svg_sha256(minified)
        meta["content_hash"] = content_hash

        if content_hash in hash_map:
            existing_id = hash_map[content_hash]
            existing_meta = next(
                (m for m in registry if m.get("id") == existing_id), None
            )
            if existing_meta is not None:
                new_quality = _metadata_quality(meta)
                old_quality = _metadata_quality(existing_meta)
                if new_quality <= old_quality:
                    print(
                        f"  [DUP ] {rel}: duplicate of {existing_id} "
                        f"(quality {new_quality} <= {old_quality}), skipping"
                    )
                    hashes.setdefault(content_hash, []).append(meta["id"])
                    duplicates += 1
                    continue
                else:
                    print(
                        f"  [DUP+] {rel}: replacing {existing_id} "
                        f"(quality {new_quality} > {old_quality})"
                    )
                    registry.remove(existing_meta)
                    hashes.setdefault(content_hash, []).append(existing_id)
                    hash_map[content_hash] = meta["id"]
            else:
                hash_map[content_hash] = meta["id"]
        else:
            hash_map[content_hash] = meta["id"]
        hashes.setdefault(content_hash, [meta["id"]])

        conf = meta["classification"]["confidence"]
        conf_counts[conf] = conf_counts.get(conf, 0) + 1

        label   = {"high": "OK", "low": "~~", "none": "??"}.get(conf, "??")
        renamed = f" -> {final_stem}.svg" if final_stem != _slugify(svg_path.stem) else ""

        print(
            f"  [{processed_count + 1:>4}/{total}] {label} "
            f"{meta['standard']:<14} {meta['category']:<20} "
            f"{svg_path.name}{renamed}"
        )

        if not args.dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / (final_stem + ".svg")).write_text(minified, encoding="utf-8")
            json_path = target_dir / (final_stem + ".json")
            with open(json_path, "w", encoding="utf-8") as fh:
                json.dump(meta, fh, indent=2, ensure_ascii=False)

        registry.append(meta)
        processed_count += 1

    registry_path = paths.PROCESSED_DIR / "registry.json"
    if not args.dry_run:
        paths.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        with open(registry_path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "schema_version": SCHEMA_VERSION,
                    "generated_at":   generated_at,
                    "total_symbols":  len(registry),
                    "symbols":        registry,
                    "hashes":         hashes,
                },
                fh,
                indent=2,
                ensure_ascii=False,
            )

    print(f"\n{'='*60}")
    print(f"  Processed  : {processed_count}")
    print(f"  Duplicates : {duplicates}")
    print(f"  Errors     : {errors}")
    print(f"  High conf  : {conf_counts.get('high', 0)}")
    print(f"  Low conf   : {conf_counts.get('low', 0)}")
    print(f"  Unknown    : {conf_counts.get('none', 0)}")
    if not args.dry_run:
        print(f"  Output    : {paths.PROCESSED_DIR}")
        print(f"  Registry  : {registry_path}")
    else:
        print("  [DRY RUN -- no files written]")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
