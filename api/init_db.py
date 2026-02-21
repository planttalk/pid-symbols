#!/usr/bin/env python3
"""init_db.py — CLI to initialise the SQLite database and manage API keys.

Usage
-----
    python api/init_db.py init
    python api/init_db.py create-key "Alice"
    python api/init_db.py create-key "Bob" --role reviewer
    python api/init_db.py list-keys
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as `python api/init_db.py` from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api import database as db


def cmd_init(_args) -> None:
    db.init_db()
    print(f"Database initialised at {db.DB_PATH}")


def cmd_create_key(args) -> None:
    role  = args.role
    token = db.create_api_key(args.label, role)
    print(f"Created {role} key for '{args.label}':")
    print(f"  Bearer {token}")


def cmd_list_keys(_args) -> None:
    from api.database import get_db
    with get_db() as conn:
        rows = conn.execute(
            "SELECT label, role, created_at, substr(key,1,8) || '…' AS key_preview "
            "FROM api_keys ORDER BY created_at"
        ).fetchall()
    if not rows:
        print("No API keys found.")
        return
    for row in rows:
        print(f"  [{row['role']:>12}]  {row['label']:<20}  {row['key_preview']}  ({row['created_at']})")


def main() -> None:
    parser = argparse.ArgumentParser(description="P&ID review API — DB management CLI")
    sub    = parser.add_subparsers(dest="cmd")

    sub.add_parser("init", help="Create database tables")

    ck = sub.add_parser("create-key", help="Create a new API key")
    ck.add_argument("label", help="Human-readable label (e.g. 'Alice')")
    ck.add_argument("--role", choices=["contributor", "reviewer"], default="contributor",
                    help="Key role (default: contributor)")

    sub.add_parser("list-keys", help="List all API keys")

    args = parser.parse_args()

    if args.cmd == "init":
        cmd_init(args)
    elif args.cmd == "create-key":
        cmd_create_key(args)
    elif args.cmd == "list-keys":
        cmd_list_keys(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
