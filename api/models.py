"""models.py — Pydantic v2 request/response models for the review API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ZoneModel(BaseModel):
    """Bounding box zone for snap point placement."""

    x: float = Field(description="X coordinate of zone origin")
    y: float = Field(description="Y coordinate of zone origin")
    width: float = Field(gt=0, description="Zone width")
    height: float = Field(gt=0, description="Zone height")


class SnapPoint(BaseModel):
    """Connection port / snap point on a symbol."""

    id: str = Field(description="Unique identifier for this snap point")
    type: str | None = Field(
        default=None, description="Port type (in, out, signal, process, etc.)"
    )
    x: float | None = Field(default=None, description="X coordinate")
    y: float | None = Field(default=None, description="Y coordinate")
    locked: bool | None = Field(
        default=None, description="Whether snap point is locked"
    )
    zone: ZoneModel | None = Field(
        default=None, description="Bounding box zone for this point"
    )


class PortSubmissionRequest(BaseModel):
    """Request to submit snap point data for review."""

    snap_points: list[SnapPoint] = Field(description="List of snap points")
    notes: str = Field(default="", description="Optional notes from contributor")


class CompleteRequest(BaseModel):
    """Request to mark symbol completion status."""

    completed: bool = Field(description="Whether symbol is marked as completed")


class ReviewRequest(BaseModel):
    """Request to review (approve/reject) a symbol."""

    approved: bool = Field(description="Whether symbol is approved")
    notes: str = Field(default="", description="Optional review notes")
