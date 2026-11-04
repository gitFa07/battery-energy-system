"""VoltTwin REST API over the same pipeline the workbench uses.

    GET  /api/v1/health       engine status (surrogate always; PyBaMM if importable) and datasheet counts
    GET  /api/v1/datasheets   cells, cooling, busbars, protection, requirements, presets, assumptions
    POST /api/v1/simulate     one design → result, conflicts, traceability, radar margins (+ time series)
    POST /api/v1/compare      several designs (default: the 3 presets) → matrix, radar, TOPSIS ranking

Run: .venv/Scripts/uvicorn src.api.main:app --reload    (docs at /docs)
"""

from __future__ import annotations

import importlib.util
from functools import lru_cache

import numpy as np
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.config import AMBIENT_REF_C, BMS_CUTOFF_C, REQUIREMENTS, T_PEAK_LIMIT_C
from src.models.db import DatasheetDB
from src.models.schemas import ModuleDesignInput
from src.physics.assumptions import ASSUMPTIONS
from src.physics.thermal import Transient
from src.pipeline import DesignEvaluation, evaluate

API_VERSION = "1.0.0"

app = FastAPI(title="VoltTwin Studio API", version=API_VERSION,
              description="Battery pack design: coupled simulation, conflict detection, traceability, ranking.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])


@lru_cache(maxsize=1)
def get_db() -> DatasheetDB:
    return DatasheetDB()


@app.exception_handler(KeyError)
async def _unknown_id(_: Request, exc: KeyError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc.args[0]) if exc.args else "not found"})


@app.exception_handler(ValueError)
async def _bad_value(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


class SimulateRequest(BaseModel):
    design: ModuleDesignInput
    use_pybamm: bool = False
    include_timeseries: bool = False
    timeseries_points: int = Field(200, ge=10, le=5000)


class CompareRequest(BaseModel):
    designs: list[ModuleDesignInput] | None = Field(None, description="omit to compare the three presets")
    use_pybamm: bool = False


def _series(tr: Transient, points: int) -> dict[str, list]:
    idx = np.unique(np.linspace(0, len(tr.t_s) - 1, min(points, len(tr.t_s))).astype(int))
    return {"t_s": tr.t_s[idx].tolist(), "phase": tr.phase[idx].tolist(), "soc": tr.soc[idx].tolist(),
            "current_a": tr.current_a[idx].tolist(), "voltage_v": tr.voltage_v[idx].tolist(),
            "t_pack_c": tr.t_pack_c[idx].tolist(), "t_core_c": tr.t_core_c[idx].tolist()}


def _design_payload(ev: DesignEvaluation) -> dict:
    return {
        "design": ev.run.design.model_dump(),
        "result": ev.run.result.model_dump(),
        "verdict": ev.ranked.verdict,
        "verdict_reasons": ev.ranked.reasons,
        "topsis_closeness": ev.ranked.closeness,
        "radar_margins": ev.ranked.margins,
        "conflicts": [a.model_dump() for a in ev.alerts if a.severity != "PASS"],
        "traceability": [t.model_dump() for t in ev.traceability],
        "round1_comparison": [vars(t) for t in ev.targets],
    }


@app.get("/api/v1/health")
def health(db: DatasheetDB = Depends(get_db)) -> dict:
    pybamm_ok = importlib.util.find_spec("pybamm") is not None
    return {"status": "ok", "version": API_VERSION,
            "engines": {"surrogate": True, "pybamm": pybamm_ok},
            "datasheets": {"cells": len(db.list_cells()), "cooling": len(db.list_cooling()),
                           "busbars": len(db.list_busbars()), "protection": len(db.list_protection()),
                           "presets": len(db.get_presets())}}


@app.get("/api/v1/datasheets")
def datasheets(db: DatasheetDB = Depends(get_db)) -> dict:
    dump = lambda items: [i.model_dump() for i in items]  # noqa: E731
    return {"cells": dump(db.list_cells()), "cooling": dump(db.list_cooling()), "busbars": dump(db.list_busbars()),
            "protection": dump(db.list_protection()), "requirements": dump(REQUIREMENTS),
            "presets": dump(db.get_presets()), "assumptions": ASSUMPTIONS,
            "limits": {"ambient_c": AMBIENT_REF_C, "t_peak_limit_c": T_PEAK_LIMIT_C, "bms_cutoff_c": BMS_CUTOFF_C}}


@app.post("/api/v1/simulate")
def simulate(req: SimulateRequest, db: DatasheetDB = Depends(get_db)) -> dict:
    ev = evaluate([req.design], db, req.use_pybamm).designs[0]
    out = _design_payload(ev)
    if req.include_timeseries:
        out["timeseries"] = {"nominal": _series(ev.run.nominal, req.timeseries_points),
                             "derated": _series(ev.run.derated, req.timeseries_points)}
    return out


@app.post("/api/v1/compare")
def compare(req: CompareRequest, db: DatasheetDB = Depends(get_db)) -> dict:
    designs = req.designs if req.designs else db.get_presets()
    study = evaluate(designs, db, req.use_pybamm)
    metrics = [r.metric for r in REQUIREMENTS]
    return {
        "matrix": {"metrics": metrics,
                   "rows": [{"design_id": ev.id, **{m: getattr(ev.run.result, m) for m in metrics},
                             "status": ev.run.result.requirement_status} for ev in study.designs]},
        "radar": {ev.id: ev.ranked.margins for ev in study.designs},
        "ranking": [{"design_id": rk.design_id, "name": rk.name, "verdict": rk.verdict,
                     "topsis_closeness": rk.closeness, "reasons": rk.reasons} for rk in study.ranking],
        "recommended": study.recommended.id if study.recommended else None,
        "designs": [_design_payload(ev) for ev in study.designs],
    }
