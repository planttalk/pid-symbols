"""server.py — FastAPI collaborative review API for P&ID symbols.

Run with:
    uvicorn api.server:app --host 0.0.0.0 --port 8000

The API is a tracking layer on top of the processed/ JSON files.
SVG and metadata are read from disk; completion/review/submission state
is stored in SQLite (api/review.db).

Authentication: Bearer token in Authorization header.
  - contributor role: read + submit ports + mark complete
  - reviewer role:    everything + approve/reject
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import database as db
from .models import CompleteRequest, PortSubmissionRequest, ReviewRequest

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = REPO_ROOT / "processed"

app = FastAPI(title="P&ID Symbol Review API", version="1.0.0")
security = HTTPBearer()


# Auth


def require_auth(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> dict:
    """Validate Bearer token; return the api_keys row."""
    row = db.get_api_key(credentials.credentials)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )
    return dict(row)


def require_reviewer(auth: Annotated[dict, Depends(require_auth)]) -> dict:
    """Ensure the authenticated user has reviewer role."""
    if auth["role"] != "reviewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Reviewer role required"
        )
    return auth


# Path safety


def _safe_symbol_path(symbol_identifier: str) -> Path:
    """Resolve symbol_id to an absolute path under PROCESSED_DIR (guard traversal)."""
    rel = symbol_identifier.replace("/", os.sep)
    try:
        resolved = (PROCESSED_DIR / rel).resolve()
        resolved.relative_to(PROCESSED_DIR.resolve())
    except (ValueError, OSError):
        raise HTTPException(status_code=400, detail="Invalid symbol identifier")
    return resolved


# Registry helper


def _load_registry() -> list[dict]:
    """Load the symbol registry from disk."""
    reg_path = PROCESSED_DIR / "registry.json"
    if not reg_path.exists():
        return []
    try:
        data = json.loads(reg_path.read_text(encoding="utf-8"))
        return data.get("symbols", [])
    except (json.JSONDecodeError, OSError):
        return []


def _merge_state(symbol: dict, state_rows: dict[str, dict]) -> dict:
    """Merge db state into a symbol dict."""
    symbol_id = symbol.get("id", "")
    state = state_rows.get(symbol_id, {})
    return {
        **symbol,
        "db_completed": bool(state.get("completed", 0)),
        "db_reviewed": bool(state.get("reviewed", 0)),
        "db_approved": state.get("approved"),
        "review_notes": state.get("review_notes", ""),
    }


# Endpoints


@app.get("/health")
def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/symbols")
def list_symbols(
    auth: Annotated[dict, Depends(require_auth)],
    status_filter: Annotated[str, Query(default="all", alias="status")] = "all",
) -> list[dict]:
    """List all symbols, optionally filtered by status.

    status: all | pending | completed | reviewed
    """
    symbols = _load_registry()
    states = {row["symbol_id"]: dict(row) for row in db.get_all_symbol_states()}

    merged = [_merge_state(s, states) for s in symbols]

    if status_filter == "completed":
        return [s for s in merged if s["db_completed"]]
    if status_filter == "pending":
        return [s for s in merged if not s["db_completed"]]
    if status_filter == "reviewed":
        return [s for s in merged if s["db_reviewed"]]

    return merged


@app.get("/symbols/{symbol_id:path}")
def get_symbol(
    symbol_id: str,
    auth: Annotated[dict, Depends(require_auth)],
) -> dict:
    """Return metadata, SVG content, db state, and submission history."""
    base = _safe_symbol_path(symbol_id)
    json_path = base.with_suffix(".json")
    svg_path = base.with_suffix(".svg")

    if not json_path.exists() or not svg_path.exists():
        raise HTTPException(status_code=404, detail="Symbol not found")

    try:
        meta = json.loads(json_path.read_text(encoding="utf-8"))
        svg = svg_path.read_text(encoding="utf-8")
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    state = db.get_symbol_state(symbol_id)
    submissions = [dict(row) for row in db.get_submissions_for_symbol(symbol_id)]

    return {
        "meta": meta,
        "svg": svg,
        "state": dict(state) if state else None,
        "submissions": submissions,
    }


@app.put("/symbols/{symbol_id:path}/ports")
def submit_ports(
    symbol_id: str,
    body: PortSubmissionRequest,
    auth: Annotated[dict, Depends(require_auth)],
) -> dict:
    """Store a port submission. Does NOT write to disk; pending reviewer approval."""
    _safe_symbol_path(symbol_id)  # validate path
    snap_json = json.dumps(
        [sp.model_dump(exclude_none=True) for sp in body.snap_points],
        ensure_ascii=False,
    )
    row_id = db.add_port_submission(symbol_id, auth["label"], snap_json, body.notes)
    return {"submission_id": row_id, "message": "Submission stored; pending review."}


@app.patch("/symbols/{symbol_id:path}/complete")
def mark_complete(
    symbol_id: str,
    body: CompleteRequest,
    auth: Annotated[dict, Depends(require_auth)],
) -> dict:
    """Contributor marks a symbol as completed (or incomplete)."""
    _safe_symbol_path(symbol_id)
    db.upsert_symbol_state(symbol_id, completed=int(body.completed))
    return {"symbol_id": symbol_id, "completed": body.completed}


@app.patch("/symbols/{symbol_id:path}/review")
def review_symbol(
    symbol_id: str,
    body: ReviewRequest,
    auth: Annotated[dict, Depends(require_reviewer)],
) -> dict:
    """Reviewer approves or rejects a symbol."""
    _safe_symbol_path(symbol_id)
    db.upsert_symbol_state(
        symbol_id,
        reviewed=1,
        approved=int(body.approved),
        review_notes=body.notes,
    )
    verdict = "approved" if body.approved else "rejected"
    return {"symbol_id": symbol_id, "verdict": verdict}


@app.get("/stats")
def get_stats(auth: Annotated[dict, Depends(require_auth)]) -> dict:
    """Overall + per-standard + per-category completion/review counts."""
    symbols = _load_registry()
    states = {row["symbol_id"]: dict(row) for row in db.get_all_symbol_states()}

    total = len(symbols)
    completed = 0
    reviewed = 0

    by_standard: dict[str, dict] = {}
    by_category: dict[str, dict] = {}

    for symbol in symbols:
        symbol_id = symbol.get("id", "")
        standard = symbol.get("standard", "unknown") or "unknown"
        category = symbol.get("category", "unknown") or "unknown"
        state = states.get(symbol_id, {})

        is_done = bool(state.get("completed", 0))
        is_reviewed = bool(state.get("reviewed", 0))

        if is_done:
            completed += 1
        if is_reviewed:
            reviewed += 1

        if standard not in by_standard:
            by_standard[standard] = {"total": 0, "completed": 0, "reviewed": 0}
        by_standard[standard]["total"] += 1
        if is_done:
            by_standard[standard]["completed"] += 1
        if is_reviewed:
            by_standard[standard]["reviewed"] += 1

        if category not in by_category:
            by_category[category] = {"total": 0, "completed": 0, "reviewed": 0}
        by_category[category]["total"] += 1
        if is_done:
            by_category[category]["completed"] += 1
        if is_reviewed:
            by_category[category]["reviewed"] += 1

    return {
        "total": total,
        "completed": completed,
        "reviewed": reviewed,
        "percentage": round(completed / total * 100, 1) if total else 0.0,
        "by_standard": by_standard,
        "by_category": by_category,
    }
