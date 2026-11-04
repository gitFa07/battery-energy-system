"""Tables shared by the workbench and the report (pandas DataFrames; no Streamlit here)."""

from __future__ import annotations

import pandas as pd

from src.config import REQUIREMENTS
from src.physics.assumptions import ASSUMPTIONS
from src.physics.replay import Replay
from src.pipeline import DesignEvaluation, StudyEvaluation

ROW_LABELS = {
    "v_nom_v": "Nominal voltage (V)", "usable_energy_kwh": "Usable energy (kWh)",
    "t_peak_c": "Peak cell temp, no derating (°C)", "t_peak_derated_c": "Peak cell temp, BMS derating (°C)",
    "t_charge_start_c": "Hottest cell at plug-in (°C)",
    "charge_time_10_80_min": "Fast charge 10–80 %, nominal (min)",
    "charge_time_derated_min": "Fast charge 10–80 %, with derating (min)",
    "mass_kg": "Module mass (kg)", "volume_l": "Module volume (L)", "bom_cost_usd": "BOM cost ($)",
    "heat_gen_w": "Charge heat generated (W)", "heat_reject_w": "Charge heat rejected (W)",
    "peak_discharge_a": "2 C peak discharge (A)",
}


def comparison_matrix(study: StudyEvaluation) -> pd.DataFrame:
    """Metric rows × design columns; Round-1 targets beside each preset where they exist."""
    data: dict[str, list] = {"Metric": list(ROW_LABELS.values())}
    for ev in study.designs:
        r = ev.run.result
        data[ev.run.design.name] = [round(float(getattr(r, k)), 2) for k in ROW_LABELS]
        if ev.targets:
            tgt = {t.metric: t.target for t in ev.targets}
            data[f"{ev.run.design.name} · Round-1"] = [tgt.get(k) for k in ROW_LABELS]
    return pd.DataFrame(data)


def requirement_grid(study: StudyEvaluation) -> pd.DataFrame:
    rows = []
    for req in REQUIREMENTS:
        limit = f"{req.min:g}–{req.max:g}" if req.min is not None and req.max is not None else \
            (f"≥ {req.min:g}" if req.min is not None else f"≤ {req.max:g}")
        row = {"Requirement": req.id, "What": req.text, "Limit": f"{limit} {req.unit}"}
        for ev in study.designs:
            v = float(getattr(ev.run.result, req.metric))
            row[ev.run.design.name] = f"{ev.run.result.requirement_status[req.id]} ({v:.2f})"
        rows.append(row)
    return pd.DataFrame(rows)


def ranking_table(study: StudyEvaluation) -> pd.DataFrame:
    return pd.DataFrame([{"Rank": i + 1, "Design": rk.name, "Verdict": rk.verdict,
                          "TOPSIS closeness": round(rk.closeness, 3), "Why": "; ".join(rk.reasons) or "—"}
                         for i, rk in enumerate(study.ranking)])


def target_gaps(study: StudyEvaluation) -> pd.DataFrame:
    rows = [{"Design": ev.run.design.name, "Metric": ROW_LABELS.get(t.metric, t.metric),
             "Simulated": round(t.simulated, 2), "Round-1": t.target, "Δ": round(t.delta, 2),
             "Tolerance": t.tolerance, "Within": "yes" if t.within else "NO", "Explanation": t.known_gap or ""}
            for ev in study.designs for t in ev.targets]
    return pd.DataFrame(rows)


def conflicts_table(ev: DesignEvaluation, include_pass: bool = False) -> pd.DataFrame:
    return pd.DataFrame([{"Rule": a.rule_id, "Family": a.rule, "Severity": a.severity,
                          "Safety": "yes" if a.safety else "", "Conflict": a.title, "Detail": a.detail,
                          "Threatens": ", ".join(a.requirements) or "—", "Fixes": "; ".join(a.fixes) or "—"}
                         for a in ev.alerts if include_pass or a.severity != "PASS"])


def traceability_table(ev: DesignEvaluation) -> pd.DataFrame:
    return pd.DataFrame([{"Requirement": t.requirement_id, "Datasheet parameters": ", ".join(t.datasheet_parameters),
                          "Physics model": t.physics_model, "Assumptions": ", ".join(t.assumptions) or "—",
                          "Metric": t.simulated_metric, "Value": round(t.value, 2), "Limit": t.limit,
                          "Status": t.status, "Evidence": t.evidence, "Validation reference": t.validation_reference}
                         for t in ev.traceability])


def assumptions_table() -> pd.DataFrame:
    return pd.DataFrame([{"Id": k, "Assumption": v} for k, v in ASSUMPTIONS.items()])


def robustness_table(rob: dict[float, dict[str, str]], names: dict[str, str]) -> pd.DataFrame:
    return pd.DataFrame([{"Cell heat factor": f"× {f:g}", **{names.get(k, k): v for k, v in verdicts.items()}}
                         for f, verdicts in rob.items()])


def replay_table(replays: list[Replay]) -> pd.DataFrame:
    return pd.DataFrame([{"Log": rp.label, "V RMSE SoC ≥ 10 % (mV)": round(rp.v_rmse_op_mv, 1),
                          "V RMSE full (mV)": round(rp.v_rmse_mv, 1), "T RMSE (K)": round(rp.t_rmse_k, 2),
                          "Rise measured (K)": round(rp.t_rise_meas_k, 2),
                          "Rise predicted (K)": round(rp.t_rise_pred_k, 2)} for rp in replays])
