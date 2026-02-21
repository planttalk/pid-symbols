"""models.py — Pydantic v2 request/response models for the review API."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ZoneModel(BaseModel):
    x:      float
    y:      float
    width:  float = Field(gt=0)
    height: float = Field(gt=0)


class SnapPoint(BaseModel):
    id:     str
    type:   Optional[str] = None
    x:      Optional[float] = None
    y:      Optional[float] = None
    locked: Optional[bool] = None
    zone:   Optional[ZoneModel] = None


class PortSubmissionRequest(BaseModel):
    snap_points: list[SnapPoint]
    notes:       str = ""


class CompleteRequest(BaseModel):
    completed: bool


class ReviewRequest(BaseModel):
    approved: bool
    notes:    str = ""
