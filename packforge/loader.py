"""Load cells, designs and studies from JSON.

A design file may `"extends": "baseline.json"` and list only what it changes, so each
option reads as an explicit diff against the starting design.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .schema import Cell, Design, Study

ROOT = Path(__file__).resolve().parent.parent
CELL_DIR = ROOT / "data" / "cells"


def deep_merge(base: dict, override: dict) -> dict:
    out = deepcopy(base)
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], val)
        else:
            out[key] = deepcopy(val)
    return out


def load_cell(cell_id: str) -> Cell:
    return Cell.model_validate_json((CELL_DIR / f"{cell_id}.json").read_text(encoding="utf-8"))


def load_design_dict(path: Path) -> dict[str, Any]:
    """Raw design dict with `extends` resolved but the cell still referenced by id."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    parent = raw.pop("extends", None)
    if parent:
        base = load_design_dict(path.parent / parent)
        # assumptions accumulate rather than replace
        extra = raw.pop("assumptions", [])
        raw = deep_merge(base, raw)
        raw["assumptions"] = base.get("assumptions", []) + extra
    return raw


def build_design(raw: dict[str, Any]) -> Design:
    data = deepcopy(raw)
    if isinstance(data.get("cell"), str):
        data["cell"] = load_cell(data["cell"]).model_dump()
    return Design.model_validate(data)


def load_design(path: Path) -> Design:
    return build_design(load_design_dict(path))


def load_study(study_dir: Path) -> tuple[Study, list[Design]]:
    """A study folder holds `study.json` plus one JSON file per design option."""
    study = Study.model_validate_json((study_dir / "study.json").read_text(encoding="utf-8"))
    designs = [load_design(p) for p in sorted(study_dir.glob("*.json")) if p.name != "study.json"]
    return study, designs
