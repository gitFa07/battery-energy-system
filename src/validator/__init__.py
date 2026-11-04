"""Conflict rules, traceability chain and TOPSIS recommender."""

from __future__ import annotations

from src.validator.conflict_engine import ConflictAlert, detect_conflicts
from src.validator.topsis_recommender import Ranked, radar_margins, recommend
from src.validator.traceability import build_traceability

__all__ = ["ConflictAlert", "Ranked", "build_traceability", "detect_conflicts", "radar_margins", "recommend"]
