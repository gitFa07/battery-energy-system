"""Margin-to-limit normalisation (radar axes) and TOPSIS ranking with automated verdicts.

Margin score per axis (0–100):  50 · (1 + headroom / span), clipped
    headroom = limit − value (≤ limits) or value − limit (≥ limits); span = limit, or limit − ambient for
    temperature. 50 = exactly at the limit, 100 = full headroom, 0 = violated by a full span.
TOPSIS: vector-normalise each criterion, weight, distance to the ideal best (d+) and worst (d−) design;
    closeness = d− / (d+ + d−) ∈ [0, 1].
Verdicts: UNSAFE = thermal requirement failed or a CRITICAL safety alert; REJECTED = any other requirement failed
    or CRITICAL alert; the eligible design with the highest closeness is OPTIMAL, other eligible ones ACCEPTABLE.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.config import REQUIREMENTS_BY_ID
from src.physics.simulate import SimulationRun
from src.validator.conflict_engine import ConflictAlert

# radar axis → requirement it is measured against
RADAR_AXES: dict[str, str] = {"Energy": "REQ-EL-02", "Thermal": "REQ-TH-01", "Cost": "REQ-EC-01",
                              "Charge": "REQ-CH-01", "Volume": "REQ-ME-02", "Mass": "REQ-ME-01"}

# TOPSIS criteria: metric → (weight, benefit?). Weights are a team choice (thermal safety and turnaround first).
CRITERIA: dict[str, tuple[float, bool]] = {
    "t_peak_c": (0.25, False),
    "charge_time_derated_min": (0.20, False),
    "usable_energy_kwh": (0.15, True),
    "bom_cost_usd": (0.15, False),
    "mass_kg": (0.125, False),
    "volume_l": (0.125, False),
}


def margin_score(req_id: str, value: float, ambient_c: float) -> float:
    req = REQUIREMENTS_BY_ID[req_id]
    if req.max is not None:
        span = req.max - ambient_c if req.unit == "°C" else req.max
        headroom = req.max - value
    else:
        span, headroom = req.min, value - req.min
    return float(np.clip(50 * (1 + headroom / span), 0, 100))


def radar_margins(run: SimulationRun) -> dict[str, float]:
    r = run.result
    return {axis: margin_score(rid, getattr(r, REQUIREMENTS_BY_ID[rid].metric), run.design.ambient_c)
            for axis, rid in RADAR_AXES.items()}


def topsis(matrix: np.ndarray, weights: np.ndarray, benefit: np.ndarray) -> np.ndarray:
    """matrix: (designs, criteria). Returns closeness to the ideal solution per design."""
    norm = np.linalg.norm(matrix, axis=0)
    v = matrix / np.where(norm == 0, 1, norm) * weights
    best = np.where(benefit, v.max(axis=0), v.min(axis=0))
    worst = np.where(benefit, v.min(axis=0), v.max(axis=0))
    d_best = np.linalg.norm(v - best, axis=1)
    d_worst = np.linalg.norm(v - worst, axis=1)
    total = d_best + d_worst
    return np.where(total == 0, 1.0, d_worst / np.where(total == 0, 1, total))


@dataclass
class Ranked:
    design_id: str
    name: str
    closeness: float
    verdict: str
    reasons: list[str]
    margins: dict[str, float]


def classify(run: SimulationRun, alerts: list[ConflictAlert]) -> tuple[str, list[str]]:
    st = run.result.requirement_status
    critical = [a for a in alerts if a.severity == "CRITICAL"]
    unsafe = [f"{a.rule_id} {a.title}" for a in critical if a.safety]
    if st.get("REQ-TH-01") == "FAIL" or unsafe:
        return "UNSAFE", ([f"REQ-TH-01 failed ({run.result.t_peak_c:.1f} °C)"] if st.get("REQ-TH-01") == "FAIL"
                          else []) + unsafe
    reasons = [f"{rid} failed" for rid, s in st.items() if s == "FAIL"] + [f"{a.rule_id} {a.title}" for a in critical]
    return ("REJECTED", reasons) if reasons else ("ELIGIBLE", [])


def recommend(runs: list[SimulationRun], alerts: dict[str, list[ConflictAlert]]) -> list[Ranked]:
    """Rank all designs; eligible ones first by closeness, then rejected, then unsafe. Sets result.verdict."""
    metrics = list(CRITERIA)
    m = np.array([[getattr(r.result, k) for k in metrics] for r in runs], dtype=float)
    w = np.array([CRITERIA[k][0] for k in metrics])
    closeness = topsis(m, w / w.sum(), np.array([CRITERIA[k][1] for k in metrics]))
    ranked = []
    for run, c in zip(runs, closeness):
        verdict, reasons = classify(run, alerts[run.design.id])
        ranked.append(Ranked(run.design.id, run.design.name, float(c), verdict, reasons, radar_margins(run)))
    order = {"ELIGIBLE": 0, "REJECTED": 1, "UNSAFE": 2}
    ranked.sort(key=lambda x: (order[x.verdict], -x.closeness))
    for i, rk in enumerate(ranked):
        if rk.verdict == "ELIGIBLE":
            rk.verdict = "OPTIMAL" if i == 0 else "ACCEPTABLE"
    by_id = {rk.design_id: rk.verdict for rk in ranked}
    for run in runs:
        run.result.verdict = by_id[run.design.id]
    return ranked
