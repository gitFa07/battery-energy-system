"""Compare simulated results with the Round-1 targets (TASK.md §1.2).

The targets are numbers from the Round-1 submission, not measurements: they are a consistency check on the
models, never a source. Tolerance: ±10 % on values, ±3 K on temperatures. Where the model and the target
disagree beyond tolerance the gap is listed in KNOWN_GAPS with the reason, and shown in the report.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.models.schemas import ModuleSimulationResult

REL_TOL = 0.10
TEMP_TOL_K = 3.0

KNOWN_GAPS: dict[tuple[str, str], str] = {
    ("baseline", "charge_time_derated_min"):
        "Round-1 68 min has no stated derating law; this model derates linearly between 50 and 55 °C on the "
        "pack (NTC) temperature, which recovers faster.",
    ("option_a", "t_peak_c"):
        "Round-1 43.1 °C implies a 3 K rise at 40 °C ambient after a ride and a 0.95 C charge; with the assumed "
        "forced-air R_th = 0.10 K/W the lumped model gives ~6 K.",
    ("option_a", "bom_cost_usd"):
        "Round-1 $275 leaves ~$82 for everything except 210 cells ($193), less than the smaller baseline needs; "
        "with the same per-part costs the model gives ~$346.",
}


@dataclass(frozen=True)
class TargetComparison:
    metric: str
    simulated: float
    target: float
    delta: float          # simulated − target
    tolerance: str
    within: bool
    known_gap: str | None


def compare_to_targets(design_id: str, result: ModuleSimulationResult, target: dict) -> list[TargetComparison]:
    rows = []
    for metric, tv in target.items():
        if metric in ("status", "verdict") or tv is None:
            continue
        sv = float(getattr(result, metric))
        if metric.endswith("_c"):
            within, tol = abs(sv - tv) <= TEMP_TOL_K, f"±{TEMP_TOL_K:g} K"
        else:
            within, tol = abs(sv - tv) <= REL_TOL * abs(tv), f"±{REL_TOL:.0%}"
        rows.append(TargetComparison(metric, sv, tv, sv - tv, tol, within, KNOWN_GAPS.get((design_id, metric))))
    return rows


def status_mismatches(result: ModuleSimulationResult, target: dict) -> dict[str, tuple[str, str]]:
    """REQ ids where the target states PASS/FAIL and the simulation disagrees: {req: (simulated, target)}."""
    return {rid: (result.requirement_status[rid], st) for rid, st in target["status"].items()
            if st is not None and result.requirement_status.get(rid) != st}
