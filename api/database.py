"""database.py — SQLite persistence layer for the collaborative review API."""
from __future__ import annotations

import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get("REVIEW_DB_PATH", Path(__file__).parent / "review.db"))

# ── Schema ─────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS api_keys (
    key       TEXT PRIMARY KEY,
    label     TEXT NOT NULL,
    role      TEXT NOT NULL DEFAULT 'contributor',  -- 'contributor' | 'reviewer'
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS symbol_states (
    symbol_id   TEXT PRIMARY KEY,
    completed   INTEGER NOT NULL DEFAULT 0,
    reviewed    INTEGER NOT NULL DEFAULT 0,
    approved    INTEGER,          -- NULL=pending, 1=approved, 0=rejected
    review_notes TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS port_submissions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol_id   TEXT NOT NULL,
    contributor TEXT NOT NULL,   -- api_key.label
    snap_points TEXT NOT NULL,   -- JSON array
    notes       TEXT NOT NULL DEFAULT '',
    submitted_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# ── Connection context manager ──────────────────────────────────────────────────

@contextmanager
def get_db():
    """Yield a committed (or rolled-back) SQLite connection."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create all tables if they don't exist yet."""
    with get_db() as conn:
        conn.executescript(_SCHEMA)


# ── API key CRUD ────────────────────────────────────────────────────────────────

def create_api_key(label: str, role: str = "contributor") -> str:
    """Generate and store a new Bearer token; return the raw token."""
    token = secrets.token_hex(32)
    with get_db() as conn:
        conn.execute(
            "INSERT INTO api_keys (key, label, role) VALUES (?, ?, ?)",
            (token, label, role),
        )
    return token


def get_api_key(token: str) -> sqlite3.Row | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT key, label, role FROM api_keys WHERE key = ?", (token,)
        ).fetchone()
    return row


# ── Symbol state CRUD ───────────────────────────────────────────────────────────

def get_symbol_state(symbol_id: str) -> sqlite3.Row | None:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM symbol_states WHERE symbol_id = ?", (symbol_id,)
        ).fetchone()


def upsert_symbol_state(symbol_id: str, **fields) -> None:
    """Insert or update a row in symbol_states with the given keyword fields."""
    allowed = {"completed", "reviewed", "approved", "review_notes"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    cols   = ", ".join(updates.keys())
    placeholders = ", ".join("?" * len(updates))
    vals   = list(updates.values())
    with get_db() as conn:
        existing = conn.execute(
            "SELECT 1 FROM symbol_states WHERE symbol_id = ?", (symbol_id,)
        ).fetchone()
        if existing:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE symbol_states SET {set_clause}, updated_at = datetime('now') WHERE symbol_id = ?",
                vals + [symbol_id],
            )
        else:
            conn.execute(
                f"INSERT INTO symbol_states (symbol_id, {cols}) VALUES (?, {placeholders})",
                [symbol_id] + vals,
            )


# ── Port submission CRUD ────────────────────────────────────────────────────────

def add_port_submission(symbol_id: str, contributor: str, snap_points_json: str, notes: str = "") -> int:
    """Store a port submission and return its row id."""
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO port_submissions (symbol_id, contributor, snap_points, notes) VALUES (?, ?, ?, ?)",
            (symbol_id, contributor, snap_points_json, notes),
        )
        return cur.lastrowid


def get_submissions_for_symbol(symbol_id: str) -> list[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM port_submissions WHERE symbol_id = ? ORDER BY submitted_at DESC",
            (symbol_id,),
        ).fetchall()


def get_all_symbol_states() -> list[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute("SELECT * FROM symbol_states").fetchall()
