#!/usr/bin/env python3
"""main.py — CLI entry point for the P&ID symbol library.

Usage:
    python main.py <command> [options]

Commands:
    process   - Classify input/ SVGs and write processed/ with normalized names
    studio    - Start the browser-based symbol editor
    api       - Start the FastAPI review API server
    help      - Show this help message

Examples:
    python main.py process
    python main.py process --dry-run
    python main.py studio
    python main.py studio --port 8080
    python main.py api
    python main.py help
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def cmd_process(args: argparse.Namespace) -> None:
    """Run the processing pipeline."""
    import json
    from datetime import datetime, timezone

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
    from src.metadata import (
        build_metadata,
        processed_dir_for,
        resolve_stem,
        _normalize_stem,
    )
    from src.svg_utils import _minify_svg
    from src.utils import _metadata_quality, _slugify, _svg_sha256
    from src.paths import Paths

    input_path: Path | None = None
    output_path: Path | None = None

    if args.input:
        input_path = Path(args.input).resolve()
    elif args.augment_source:
        input_path = (Paths.REPO_ROOT / args.augment_source).resolve()

    if args.output:
        output_path = Path(args.output).resolve()
    elif args.input or args.augment_source or args.augment:
        if input_path:
            output_path = input_path.parent / f"{input_path.name}-augmented"

    if input_path or output_path:
        Paths.configure(input_dir=input_path, output_dir=output_path)

    if args.export_completed:
        export_dir = Path(args.export_completed).resolve()
        source_dir = (
            Path(args.export_source).resolve()
            if args.export_source
            else Paths.PROCESSED_DIR
        )
        export_completed_symbols(source_dir, export_dir, args.dry_run)
        return

    if args.migrate:
        migrate_to_source_hierarchy(Paths.PROCESSED_DIR, args.dry_run)
        return

    if args.dedup_input:
        dedup_input(Paths.INPUT_DIR, args.dry_run)
        return

    if args.migrate_legacy_completed:
        migrate_legacy_completed(paths.PROCESSED_DIR, args.dry_run)
        return

    if args.export_yolo:
        yolo_out = Path(args.export_yolo).resolve()
        registry_path = paths.PROCESSED_DIR / "registry.json"
        export_yolo_datasets(
            registry_path,
            yolo_out,
            args.augment_count,
            args.dry_run,
            args.augment_min_size,
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
        augment_svgs(
            paths.INPUT_DIR,
            paths.PROCESSED_DIR,
            args.augment_count,
            args.dry_run,
            args.augment_min_size,
        )
        return

    generated_at = datetime.now(timezone.utc).isoformat()

    svg_files = sorted(paths.INPUT_DIR.rglob("*.svg"))
    total = len(svg_files)
    print(f"Found {total} SVG files under {paths.INPUT_DIR}\n")

    registry: list[dict] = []
    processed_count = 0
    errors = 0
    conf_counts: dict[str, int] = {}

    used_stems: dict[Path, set[str]] = {}
    hash_map: dict[str, str] = {}
    hashes: dict[str, list[str]] = {}
    duplicates = 0

    for svg_path in svg_files:
        if "_debug" in svg_path.stem:
            continue
        rel = svg_path.relative_to(paths.REPO_ROOT)
        src_rel = str(rel).replace("\\", "/")
        try:
            classification = classify(svg_path)
            target_dir = processed_dir_for(classification, src_rel)

            if target_dir not in used_stems:
                used_stems[target_dir] = set()

            base_stem = _normalize_stem(svg_path.stem, classification.standard)
            final_stem = resolve_stem(base_stem, target_dir, used_stems[target_dir])
            meta = build_metadata(svg_path, final_stem, classification, src_rel)
        except Exception as exc:
            print(f"  [ERROR] {rel}: {exc}")
            errors += 1
            continue

        raw_svg = svg_path.read_text(encoding="utf-8", errors="replace")
        minified = _minify_svg(raw_svg)
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

        label = {"high": "OK", "low": "~~", "none": "??"}.get(conf, "??")
        renamed = (
            f" -> {final_stem}.svg" if final_stem != _slugify(svg_path.stem) else ""
        )

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
                    "generated_at": generated_at,
                    "total_symbols": len(registry),
                    "symbols": registry,
                    "hashes": hashes,
                },
                fh,
                indent=2,
                ensure_ascii=False,
            )

    print(f"\n{'=' * 60}")
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
    print(f"{'=' * 60}")


def cmd_studio(args: argparse.Namespace) -> None:
    """Start the browser-based symbol editor."""
    from src.studio import server as studio_server
    from src.studio import symbols as studio_symbols
    from src.studio import reports as studio_reports

    repo_root = Path(__file__).parent
    symbols_root = (
        Path(args.symbols).resolve() if args.symbols else repo_root / "processed"
    )
    editor_root = repo_root / "editor"
    editor_dir = (
        editor_root / "dist" if (editor_root / "dist").is_dir() else editor_root
    )
    reports_file = repo_root / "unrealistic_reports.json"

    if not symbols_root.is_dir():
        print(f"Error: symbols directory not found: {symbols_root}")
        return

    studio_symbols.set_symbols_root(symbols_root)
    studio_reports.set_reports_file(reports_file)
    studio_server.set_editor_dir(editor_dir)
    studio_server.set_server_config(args.port, args.host)

    print(f"Symbols root → {symbols_root}")
    studio_server.run_server()


def cmd_api(args: argparse.Namespace) -> None:
    """Start the FastAPI review API server."""
    try:
        import uvicorn
    except ImportError:
        print("Error: uvicorn not installed. Install with: pip install uvicorn")
        return

    host = args.host
    port = args.port
    reload = args.reload

    print(f"Starting API server at http://{host}:{port}")
    uvicorn.run(
        "api.server:app",
        host=host,
        port=port,
        reload=reload,
    )


def cmd_help(args: argparse.Namespace) -> None:
    """Show help message."""
    parser.print_help()


def main() -> None:
    global parser

    parser = argparse.ArgumentParser(
        description="P&ID Symbol Library CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py process
  python main.py process --dry-run
  python main.py process --augment --augment-count 5
  python main.py studio
  python main.py studio --port 8080
  python main.py api
  python main.py api --reload
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # process subcommand
    process_parser = subparsers.add_parser(
        "process",
        help="Classify input/ SVGs and write processed/",
    )
    process_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and classify without writing files",
    )
    process_parser.add_argument(
        "--input", default=None, metavar="DIR", help="Input directory to scan for SVGs"
    )
    process_parser.add_argument(
        "--output",
        default=None,
        metavar="DIR",
        help="Output directory for processed files",
    )
    process_parser.add_argument(
        "--augment",
        action="store_true",
        help="Generate augmented PNGs instead of processed SVG/JSON",
    )
    process_parser.add_argument(
        "--augment-count",
        type=int,
        default=5,
        metavar="N",
        help="Number of augmented PNGs per SVG",
    )
    process_parser.add_argument(
        "--augment-min-size",
        type=int,
        default=256,
        metavar="PX",
        help="Minimum short-side size in pixels",
    )
    process_parser.add_argument(
        "--augment-source",
        choices=["completed", "processed"],
        default=None,
        help="Use completed/ or processed/ as input",
    )
    process_parser.add_argument(
        "--export-completed",
        default=None,
        metavar="DIR",
        help="Export completed symbols to DIR",
    )
    process_parser.add_argument(
        "--export-source",
        default=None,
        metavar="DIR",
        help="Source symbols root for export",
    )
    process_parser.add_argument(
        "--migrate",
        action="store_true",
        help="Migrate processed/ to source-aware hierarchy",
    )
    process_parser.add_argument(
        "--export-yolo", default=None, metavar="DIR", help="Export YOLO datasets to DIR"
    )
    process_parser.add_argument(
        "--compose-count",
        type=int,
        default=20,
        metavar="N",
        help="Composite images per standard",
    )
    process_parser.add_argument(
        "--dedup-input",
        action="store_true",
        help="Delete duplicate SVG files from input",
    )
    process_parser.add_argument(
        "--migrate-legacy-completed",
        action="store_true",
        help="Merge legacy completed symbols",
    )

    # studio subcommand
    studio_parser = subparsers.add_parser(
        "studio",
        help="Start the browser-based symbol editor",
    )
    studio_parser.add_argument(
        "--symbols",
        default=None,
        metavar="DIR",
        help="Path to symbols root directory (default: ./processed)",
    )
    studio_parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", 7421)),
        metavar="PORT",
        help="Local HTTP port (default: 7421)",
    )
    studio_parser.add_argument(
        "--host",
        default=os.environ.get("HOST", "127.0.0.1"),
        metavar="ADDR",
        help="Bind address (default: 127.0.0.1)",
    )

    # api subcommand
    api_parser = subparsers.add_parser(
        "api",
        help="Start the FastAPI review API server",
    )
    api_parser.add_argument(
        "--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)"
    )
    api_parser.add_argument(
        "--port", type=int, default=8000, help="Port (default: 8000)"
    )
    api_parser.add_argument("--reload", action="store_true", help="Enable auto-reload")

    # help subcommand
    subparsers.add_parser("help", help="Show this help message")

    args = parser.parse_args()

    if args.command == "process":
        cmd_process(args)
    elif args.command == "studio":
        cmd_studio(args)
    elif args.command == "api":
        cmd_api(args)
    elif args.command == "help" or args.command is None:
        cmd_help(args)
    else:
        parser.print_help()


import os

if __name__ == "__main__":
    main()
