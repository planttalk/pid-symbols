"""Google Cloud Storage sync module.

Upsert-style sync from local category directories to a GCS bucket,
with optional orphan deletion for GCS objects not present locally.

Environment:
    GCS_BUCKET_NAME  Override the default bucket (pid_automation_labs).
    Standard ADC / GOOGLE_APPLICATION_CREDENTIALS for auth.
"""

from __future__ import annotations

import base64
import hashlib
import os
import threading
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Iterator, TypeAlias

# Runtime import — guarded so the module loads even without the GCS package.
try:
    from google.cloud import storage as _gcs_storage
    from google.api_core import exceptions as _gcs_exceptions

    _GCS_AVAILABLE = True
except ImportError:
    _GCS_AVAILABLE = False

# Type-checker-only imports: zero runtime cost, full IDE support.
if TYPE_CHECKING:
    from google.cloud.storage import Bucket as GCSBucket
    from google.cloud.storage import Client as GCSClient

__all__ = ["GCSSyncManager", "SyncCategory", "SyncEvent", "get_sync_manager"]


# ── Constants ─────────────────────────────────────────────────────────────────

_BUCKET_ENV_KEY = "GCS_BUCKET_NAME"
_DEFAULT_BUCKET = "pid_automation_labs"

# Stem fragment that marks auto-generated debug overlays — never sync these.
_DEBUG_STEM_MARKER = "_debug"

_SKIP_DIRS: frozenset[str] = frozenset(
    {"__pycache__", ".git", "node_modules", ".venv", "dist"}
)
_SKIP_SUFFIXES: frozenset[str] = frozenset({".pyc", ".pyo", ".pyd"})

# Chunk size for MD5 streaming: 1 MiB balances memory vs syscall overhead.
_READ_CHUNK_BYTES = 1 << 20


# ── Types ─────────────────────────────────────────────────────────────────────


class SyncCategory(StrEnum):
    INPUT = "input"
    PROCESSED = "processed"
    AUGMENTED = "augmented"


# SSE event payload — a plain dict so JSON serialisation stays trivial.
SyncEvent: TypeAlias = dict[str, object]


@dataclass(slots=True)
class _SyncCounters:
    """Mutable tally accumulated during a single sync pass."""

    uploaded: int = 0
    skipped: int = 0
    deleted: int = 0
    errors: int = 0


# ── Pure helpers ──────────────────────────────────────────────────────────────


def _resolve_bucket_name() -> str:
    """Return the configured bucket name, falling back to the project default."""
    return os.environ.get(_BUCKET_ENV_KEY, _DEFAULT_BUCKET)


def _local_dir(category: SyncCategory, repo_root: Path) -> Path:
    return repo_root / category.value


def _gcs_prefix(category: SyncCategory) -> str:
    # GCS "directory" prefixes must end with a slash.
    return category.value + "/"


def _compute_md5_b64(file_path: Path) -> str:
    """Return base64-encoded MD5 digest matching the GCS ``md5_hash`` field.

    Args:
        file_path: Local file to hash.

    Returns:
        Base64-encoded MD5 string (e.g. ``"rL0Y20zC+Fzt72VPzMSk2A=="``).

    Raises:
        OSError: If the file cannot be opened or read.
    """
    hasher = hashlib.md5(usedforsecurity=False)
    with file_path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(_READ_CHUNK_BYTES), b""):
            hasher.update(chunk)
    return base64.b64encode(hasher.digest()).decode("ascii")


def _file_has_changed(local_path: Path, remote_md5: str) -> bool:
    """Return True when the local file differs from the remote GCS object.

    Falls back to True when the file is unreadable so the caller always
    schedules an upload rather than silently skipping a broken file.

    Args:
        local_path: Local file to inspect.
        remote_md5: Base64-encoded MD5 from the GCS blob metadata.

    Returns:
        True if the content has changed or cannot be verified.
    """
    try:
        return _compute_md5_b64(local_path) != remote_md5
    except OSError:
        # Unreadable file: treat as changed to force a re-upload attempt.
        return True


def _should_skip(relative: Path) -> bool:
    """Return True if *relative* should be excluded from sync.

    Args:
        relative: Path relative to the category root directory.

    Returns:
        True for hidden paths, skip-listed directories, excluded suffixes,
        and auto-generated debug overlay files.
    """
    parts = relative.parts
    if any(part.startswith(".") for part in parts):
        return True
    if any(part in _SKIP_DIRS for part in parts):
        return True
    if relative.suffix.lower() in _SKIP_SUFFIXES:
        return True
    return _DEBUG_STEM_MARKER in relative.stem


def _collect_local_files(local_dir: Path, prefix: str) -> dict[str, Path]:
    """Map GCS blob names to their local paths for all eligible files.

    Args:
        local_dir: Root directory to scan recursively.
        prefix:    GCS prefix (e.g. ``"input/"``) prepended to each relative path.

    Returns:
        Dict mapping blob names to local ``Path`` objects, sorted for
        deterministic ordering during sync.
    """
    result: dict[str, Path] = {}
    for file_path in sorted(local_dir.rglob("*")):
        if not file_path.is_file():
            continue
        relative = file_path.relative_to(local_dir)
        if _should_skip(relative):
            continue
        result[prefix + relative.as_posix()] = file_path
    return result


def _build_counter_summary(counters: _SyncCounters) -> dict[str, int]:
    """Serialise *counters* to a plain dict for SSE payload embedding."""
    return {
        "uploaded": counters.uploaded,
        "skipped": counters.skipped,
        "deleted": counters.deleted,
        "errors": counters.errors,
    }


# ── Manager ───────────────────────────────────────────────────────────────────


class GCSSyncManager:
    """Upsert-style sync between local category directories and a GCS bucket.

    Args:
        repo_root:   Repository root; category directories are resolved here.
        bucket_name: GCS bucket name. Falls back to ``GCS_BUCKET_NAME`` env var,
                     then to ``pid_automation_labs``.
        client:      Optional pre-configured GCS client for dependency injection
                     and testing. When ``None``, a client is lazily created from
                     Application Default Credentials on first use.
    """

    __slots__ = ("_repo_root", "_bucket_name", "_client", "_bucket")

    def __init__(
        self,
        repo_root: Path,
        bucket_name: str | None = None,
        client: GCSClient | None = None,
    ) -> None:
        self._repo_root = repo_root
        self._bucket_name = bucket_name or _resolve_bucket_name()
        self._client: GCSClient | None = client
        self._bucket: GCSBucket | None = None

    # ── Connection ────────────────────────────────────────────────────────────

    def _ensure_client(self) -> None:
        """Lazily initialise the GCS client and bucket handle from ADC."""
        if not _GCS_AVAILABLE:
            raise RuntimeError("google-cloud-storage is not installed")
        if self._client is None:
            self._client = _gcs_storage.Client()
        if self._bucket is None:
            self._bucket = self._client.bucket(self._bucket_name)

    def get_status(self) -> dict[str, object]:
        """Return GCS connection status and bucket metadata.

        Returns:
            Dict with ``connected: True`` and bucket details on success,
            or ``connected: False`` with an ``error`` string on failure.
        """
        if not _GCS_AVAILABLE:
            return {"connected": False, "error": "google-cloud-storage not installed"}
        try:
            self._ensure_client()
            bucket = self._client.get_bucket(self._bucket_name)
            return {
                "connected": True,
                "bucket": bucket.name,
                "location": bucket.location,
                "storage_class": bucket.storage_class,
            }
        except _gcs_exceptions.NotFound:
            return {"connected": False, "error": "Bucket not found"}
        except _gcs_exceptions.Forbidden:
            return {"connected": False, "error": "Access denied — check credentials"}
        except Exception as exc:  # noqa: BLE001 — surface all GCS errors to the UI
            return {"connected": False, "error": str(exc)}

    # ── Sync ──────────────────────────────────────────────────────────────────

    def sync(
        self,
        category: SyncCategory,
        *,
        delete_orphans: bool = False,
        cancel: threading.Event | None = None,
    ) -> Iterator[SyncEvent]:
        """Yield SSE-compatible progress events while syncing *category*.

        Args:
            category:       Which local directory / GCS prefix to sync.
            delete_orphans: When True, GCS objects absent locally are deleted.
            cancel:         Optional threading event; when set, the sync stops at
                            the next file boundary and yields a ``cancelled`` event.

        Yields:
            SyncEvent dicts keyed on ``type``:

            - ``start``      — ``{category, total, to_upload, to_skip, to_delete}``
            - ``progress``   — ``{action: upload|skip|delete, file, done, total}``
            - ``file_error`` — ``{file, message}``
            - ``done``       — ``{uploaded, skipped, deleted, errors}``
            - ``cancelled``  — ``{uploaded, skipped, deleted, errors}``
            - ``error``      — ``{message}`` — fatal; generator stops immediately
        """
        local_dir = _local_dir(category, self._repo_root)
        prefix = _gcs_prefix(category)

        if not local_dir.is_dir():
            yield {"type": "error", "message": f"Directory not found: {local_dir}"}
            return

        try:
            self._ensure_client()
        except Exception as exc:  # noqa: BLE001
            yield {"type": "error", "message": f"GCS connection failed: {exc}"}
            return

        local_files = _collect_local_files(local_dir, prefix)

        try:
            remote_md5_by_blob: dict[str, str] = {
                blob.name: (blob.md5_hash or "")
                for blob in self._client.list_blobs(self._bucket_name, prefix=prefix)
            }
        except Exception as exc:  # noqa: BLE001
            yield {"type": "error", "message": f"Failed to list GCS objects: {exc}"}
            return

        to_upload, to_skip, to_delete = self._partition_files(
            local_files, remote_md5_by_blob, delete_orphans
        )
        total = len(to_upload) + len(to_skip) + len(to_delete)

        yield {
            "type": "start",
            "category": category.value,
            "total": total,
            "to_upload": len(to_upload),
            "to_skip": len(to_skip),
            "to_delete": len(to_delete),
        }

        counters = _SyncCounters()
        files_processed = 0

        for blob_name, local_path in to_upload:
            if cancel and cancel.is_set():
                yield {"type": "cancelled", **_build_counter_summary(counters)}
                return
            upload_error = self._upload_file(blob_name, local_path)
            files_processed += 1
            if upload_error:
                counters.errors += 1
                yield {"type": "file_error", "file": blob_name, "message": upload_error}
            else:
                counters.uploaded += 1
            yield {
                "type": "progress",
                "action": "upload",
                "file": blob_name,
                "done": files_processed,
                "total": total,
            }

        for blob_name in to_skip:
            if cancel and cancel.is_set():
                yield {"type": "cancelled", **_build_counter_summary(counters)}
                return
            counters.skipped += 1
            files_processed += 1
            yield {
                "type": "progress",
                "action": "skip",
                "file": blob_name,
                "done": files_processed,
                "total": total,
            }

        for blob_name in to_delete:
            if cancel and cancel.is_set():
                yield {"type": "cancelled", **_build_counter_summary(counters)}
                return
            delete_error = self._delete_blob(blob_name)
            files_processed += 1
            if delete_error:
                counters.errors += 1
                yield {"type": "file_error", "file": blob_name, "message": delete_error}
            else:
                counters.deleted += 1
            yield {
                "type": "progress",
                "action": "delete",
                "file": blob_name,
                "done": files_processed,
                "total": total,
            }

        yield {"type": "done", **_build_counter_summary(counters)}

    # ── Private ───────────────────────────────────────────────────────────────

    def _partition_files(
        self,
        local_files: dict[str, Path],
        remote_md5_by_blob: dict[str, str],
        delete_orphans: bool,
    ) -> tuple[list[tuple[str, Path]], list[str], list[str]]:
        """Partition files into upload / skip / delete work lists.

        Args:
            local_files:        Blob name → local path mapping.
            remote_md5_by_blob: Blob name → GCS MD5 hash mapping.
            delete_orphans:     When True, populates the delete list.

        Returns:
            Three-tuple of (to_upload, to_skip, to_delete) lists.
        """
        to_upload: list[tuple[str, Path]] = []
        to_skip: list[str] = []

        for blob_name, local_path in local_files.items():
            remote_md5 = remote_md5_by_blob.get(blob_name)
            is_new_or_changed = remote_md5 is None or _file_has_changed(local_path, remote_md5)
            if is_new_or_changed:
                to_upload.append((blob_name, local_path))
            else:
                to_skip.append(blob_name)

        if not delete_orphans:
            return to_upload, to_skip, []

        local_blob_names = set(local_files)
        to_delete = [name for name in remote_md5_by_blob if name not in local_blob_names]
        return to_upload, to_skip, to_delete

    def _upload_file(self, blob_name: str, local_path: Path) -> str:
        """Upload *local_path* to GCS as *blob_name*.

        Returns:
            Empty string on success, or an error message string on failure.
        """
        try:
            self._bucket.blob(blob_name).upload_from_filename(str(local_path))
            return ""
        except Exception as exc:  # noqa: BLE001
            return str(exc)

    def _delete_blob(self, blob_name: str) -> str:
        """Delete *blob_name* from GCS.

        Returns:
            Empty string on success, or an error message string on failure.
        """
        try:
            self._bucket.blob(blob_name).delete()
            return ""
        except Exception as exc:  # noqa: BLE001
            return str(exc)


# ── Module-level singleton ────────────────────────────────────────────────────

# A module-level reference is acceptable here: the HTTP server is single-process
# and the GCS client library manages its own internal connection pool, so sharing
# one manager instance across request threads is safe.
_sync_manager: GCSSyncManager | None = None


def get_sync_manager(repo_root: Path | None = None) -> GCSSyncManager:
    """Return the module-level GCSSyncManager singleton.

    Args:
        repo_root: Repository root for resolving category directories.
                   Defaults to the grandparent of this file (the repo root).

    Returns:
        The shared GCSSyncManager instance.
    """
    global _sync_manager  # noqa: PLW0603 — intentional module-level singleton
    if _sync_manager is None:
        root = repo_root or Path(__file__).resolve().parent.parent
        _sync_manager = GCSSyncManager(repo_root=root)
    return _sync_manager
