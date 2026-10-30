"""PackForge workbench UI.  Run: streamlit run app.py"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from packforge import figures
from packforge.engine import (DesignResult, monte_carlo, rank, recommend, run_design, traceability,
                              with_heat_factor)
from packforge.fit import FitResult, Log, LogFit, evaluate, fit, load_calibration
from packforge.loader import CELL_DIR, ROOT, build_design, deep_merge, load_cell, load_design_dict
from packforge.metrics import KPIS, METRICS, fmt
from packforge.report import build_report
from packforge.schema import Design, Study

STATUS_ICON = {"pass": "✅", "warn": "⚠️", "fail": "❌"}
VALIDATION_DIR = ROOT / "data" / "validation"

st.set_page_config(page_title="PackForge", page_icon="🔋", layout="wide")


@st.cache_data(show_spinner="Simulating…")
def cached_run(design_json: str, study_json: str) -> DesignResult:
    return run_design(Design.model_validate_json(design_json), Study.model_validate_json(study_json))


@st.cache_data(show_spinner="Sampling cell variation…")
def cached_mc(design_json: str, study_json: str, n: int) -> dict[str, np.ndarray]:
    return monte_carlo(Design.model_validate_json(design_json), Study.model_validate_json(study_json), n=n)


@st.cache_data(show_spinner="Fitting cell model to the log (~30 s)…")
def cached_fit(log_name: str, cell_id: str) -> FitResult:
    return fit(Log.read(VALIDATION_DIR / log_name), load_cell(cell_id))


@st.cache_data(show_spinner="Replaying the log…")
def cached_eval(cell_id: str, h_eff: float, c_th: float | None, log_name: str) -> LogFit:
    return evaluate(load_cell(cell_id), h_eff, Log.read(VALIDATION_DIR / log_name), c_th=c_th)


# ---------------------------------------------------------------- sidebar: study, designs, what-if
studies = sorted(p for p in (ROOT / "studies").iterdir() if (p / "study.json").exists())
study_dir = st.sidebar.selectbox("Study", studies, format_func=lambda p: p.name)
study = Study.model_validate_json((study_dir / "study.json").read_text(encoding="utf-8"))
raw = {p.stem: load_design_dict(p) for p in sorted(study_dir.glob("*.json")) if p.name != "study.json"}

chosen = st.sidebar.multiselect("Designs", list(raw), default=list(raw))
study = study.model_copy(update={"ambient_c": st.sidebar.slider("Ambient °C", 0, 50, int(study.ambient_c))})
charge_sc = study.scenarios["charge"]
hot = st.sidebar.toggle("Charge right after the ride (pack still hot)", value=charge_sc.after is not None)
study = study.model_copy(update={"scenarios": {**study.scenarios, "charge": charge_sc.model_copy(
    update={"after": (charge_sc.after or "drive") if hot else None})}})

heat = st.sidebar.slider("Unmodelled heat ×", 1.0, 2.5, 1.0, 0.1,
                         help="Model uncertainty: the hold-out check under-predicts the measured temperature rise "
                              "by up to ~2× (Validation tab). Multiplies heat in every cell; the BMS observer is not "
                              "told.")

with st.sidebar.expander("🔧 What-if variant", expanded=True):
    base_key = st.selectbox("Start from", list(raw))
    b = raw[base_key]
    enabled = st.checkbox("Add what-if to comparison", value=False)
    placements = ["edge", "spread", "center"]
    overrides = {
        "id": "what_if", "name": f"What-if ({base_key})",
        "topology": {"parallel": st.slider("Parallel cells", 4, 16, b["topology"]["parallel"])},
        "control": {
            "charge_c_rate": st.slider("Charge C-rate", 0.2, 2.0, float(b["control"]["charge_c_rate"]), 0.05),
            "derate_start_c": st.slider("Derate start °C", 30.0, 60.0, float(b["control"]["derate_start_c"]), 0.5),
            "derate_end_c": st.slider("Derate end °C", 30.0, 60.0, float(b["control"]["derate_end_c"]), 0.5),
            "derate_on": st.radio("Derate on", ["sensed", "observer"], horizontal=True,
                                  index=["sensed", "observer"].index(b["control"].get("derate_on", "sensed"))),
        },
        "cooling": {"h_eff_w_m2k": st.slider("Cooling h_eff W/m²K", 0.5, 40.0, float(b["cooling"]["h_eff_w_m2k"]), 0.5)},
        "sensing": {
            "n_temp_sensors": st.slider("Temp sensors", 1, 12, b["sensing"]["n_temp_sensors"]),
            "placement": st.selectbox("Sensor placement", placements,
                                      index=placements.index(b["sensing"]["placement"])
                                      if isinstance(b["sensing"]["placement"], str) else 1),
        },
    }

designs = [build_design(raw[k]) for k in chosen]
if enabled:
    designs.append(build_design(deep_merge(b, overrides)))
if not designs:
    st.info("Select at least one design.")
    st.stop()
designs = [with_heat_factor(d, heat) for d in designs] if heat != 1 else designs

study_json = study.model_dump_json()
results = [cached_run(d.model_dump_json(), study_json) for d in designs]
names = [r.design.name for r in results]

# ---------------------------------------------------------------- header + recommendation
st.title("🔋 PackForge — battery design workbench")
st.caption(f"{study.application} · ambient {study.ambient_c:g} °C · "
           + ("charging right after the ride" if hot else "charging from ambient")
           + (f" · cells generate {heat:g}× the modelled heat" if heat != 1 else ""))

ranking = rank(results, study)
recs = recommend(results, study)
if recs:
    for rec, show in zip(recs, (st.success, st.info, st.info)):
        show(f"**{rec.headline}** — {rec.why}")
else:
    st.error("No design meets every *must* requirement and interface rule — see Conflicts.")
stress = [cached_run(with_heat_factor(d, max(heat, 2.0)).model_dump_json(), study_json) for d in designs]
st.download_button("⬇️ Download design report (HTML)", build_report(results, study, stress),
                   file_name="packforge_report.html", mime="text/html")

tabs = st.tabs(["Compare", "Time series", "Heat map", "Conflicts", "Traceability", "Monte Carlo", "Validation"])

# ---------------------------------------------------------------- compare
with tabs[0]:
    status = {r.design.id: {f.requirement: f.severity for f in r.findings if f.requirement} for r in results}
    req_by_metric = {q.metric: q.id for q in study.requirements}
    rows = []
    for k in KPIS:
        row = {"KPI": METRICS[k].label, "Evidence": METRICS[k].evidence}
        for r in results:
            sev = status[r.design.id].get(req_by_metric.get(k), "")
            row[r.design.name] = f"{STATUS_ICON.get(sev, '')} {fmt(k, r.metrics[k])}".strip()
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    c1, c2 = st.columns([3, 2])
    c1.plotly_chart(figures.radar(results, study), width="stretch")
    with c2:
        st.subheader("Ranking")
        for i, rk in enumerate(ranking, 1):
            nm = next(r.design.name for r in results if r.design.id == rk.design_id)
            st.markdown(f"{i}. **{nm}** — {rk.score:.0f}" + ("" if rk.eligible else " · ❌ disqualified"))
        st.caption("Score = weighted min-max normalised KPIs (weights in study.json). Any failed *must* "
                   "requirement or interface rule disqualifies a design. The thermal-limit bound is an independent "
                   "hand calculation (cold start) that cross-checks the simulated charge time.")

# ---------------------------------------------------------------- time series
with tabs[1]:
    which = st.radio("Scenario", ["charge", "drive"], horizontal=True)
    picked = st.multiselect("Signals", list(figures.SIGNALS), default=["Max cell temp °C", "BMS hotspot view °C"])
    for label in picked:
        st.plotly_chart(figures.timeseries(results, which, label), width="stretch")
    for r in results:
        st.caption(f"{r.design.name} — {which}: " + " · ".join(getattr(r, which).events[0]))

# ---------------------------------------------------------------- heat map
with tabs[2]:
    st.caption("Cell temperatures at the moment the hottest cell peaked. ◯ = BMS temperature sensor.")
    for col, r in zip(st.columns(len(results)), results):
        col.plotly_chart(figures.heatmap(r), width="stretch")

# ---------------------------------------------------------------- conflicts
with tabs[3]:
    for r in results:
        issues = r.fails + r.warns
        st.subheader(f"{r.design.name} — {len(r.fails)} fail · {len(r.warns)} warn")
        if not issues:
            st.write("✅ No conflicts.")
        for f in issues:
            with st.expander(f"{STATUS_ICON[f.severity]} {f.id} · {f.title}", expanded=f.severity == "fail"):
                st.markdown(f"**Subsystems:** {', '.join(f.subsystems)}  \n**Why:** {f.detail}")
                if f.fixes:
                    st.markdown("**Candidate fixes:**\n" + "\n".join(f"- {x}" for x in f.fixes))

# ---------------------------------------------------------------- traceability
with tabs[4]:
    st.caption("Evidence ladder: datasheet → assumption → calculated → estimated → simulated → measured")
    r = results[st.selectbox("Design", range(len(results)), format_func=lambda i: names[i])]
    st.dataframe(pd.DataFrame(traceability(r, study)), hide_index=True, width="stretch")
    st.markdown("**Assumptions**")
    st.dataframe(pd.DataFrame([a.model_dump() for a in r.design.all_assumptions()]), hide_index=True, width="stretch")
    st.markdown("**Data sources:** " + "; ".join(r.design.cell.sources))
    st.download_button("Download design (JSON)", json.dumps(r.design.model_dump(), indent=2, ensure_ascii=False),
                       file_name=f"{r.design.id}.json")

# ---------------------------------------------------------------- monte carlo
with tabs[5]:
    st.caption("Samples cell-to-cell capacity and resistance spread, then simulates every pack.")
    i = st.selectbox("Design ", range(len(results)), format_func=lambda i: names[i])
    n = st.slider("Packs to sample", 10, 200, 50, 10)
    if st.button("Run Monte Carlo"):
        mc = cached_mc(designs[i].model_dump_json(), study_json, n)
        for c, k in zip(st.columns(3), ["usable_energy_wh", "charge_time_min", "t_max_charge_c"]):
            v = mc[k]
            fig = go.Figure(go.Histogram(x=v, nbinsx=20))
            fig.update_layout(title=f"{METRICS[k].label}<br><sup>mean {v.mean():.1f} · P5 "
                                    f"{np.percentile(v, 5):.1f} · P95 {np.percentile(v, 95):.1f}</sup>", height=320)
            c.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------- validation
with tabs[6]:
    for cell_id in dict.fromkeys(r.design.cell.id for r in results):
        cal = load_calibration(cell_id)
        cell_name = next(r.design.cell.name for r in results if r.design.cell.id == cell_id)
        if cal is None:
            st.warning(f"**{cell_name}** — not validated against measured data (datasheet/class values only).")
            continue
        st.subheader(f"Calibration — {cell_name}")
        st.caption(f"Proxy cell: {cal['proxy']}. Fitted on {len(cal['fit_logs'])} logs at 25–35 °C; hold-out at "
                   f"{cal['holdout_temp_c']} °C on logs and a temperature the fit never saw. Voltage RMSE over the "
                   f"operating window (SOC ≥ {cal['op_soc_min']:.0%}); full-range figures below.")
        cols = st.columns(4)
        for col, (kind, sm) in zip((cols[:2], cols[2:]), cal["holdout_summary"].items()):
            col[0].metric(f"Hold-out {kind}s: V RMSE (median)", f"{sm['v_rmse_op_mv_median']:.0f} mV",
                          f"max {sm['v_rmse_op_mv_max']:.0f} mV · n={sm['n']}", delta_color="off")
            col[1].metric(f"Hold-out {kind}s: T rise meas / model", f"{sm['t_rise_meas_k_mean']:.1f} / "
                          f"{sm['t_rise_pred_k_mean']:.1f} K", f"T RMSE median {sm['t_rmse_k_median']:.2f} K",
                          delta_color="off")
        uncal = CELL_DIR / f"{cell_id}_uncalibrated.json"
        if uncal.exists():
            before, after = load_cell(f"{cell_id}_uncalibrated"), load_cell(cell_id)
            keys = ["capacity_ah", "r0_ohm", "r1_ohm", "tau_s", "r_temp_k"]
            st.dataframe(pd.DataFrame({"parameter": keys, "generic (before)": [getattr(before, k) for k in keys],
                                       "calibrated": [getattr(after, k) for k in keys]}), hide_index=True)
        with st.expander("All fit and hold-out logs"):
            st.dataframe(pd.DataFrame([r | {"set": "fit"} for r in cal["fit"]]
                                      + [r | {"set": f"hold-out {k}"} for k, rows in cal["holdout"].items()
                                         for r in rows]), hide_index=True, width="stretch")
        replay = sorted(p.name for p in VALIDATION_DIR.glob("TUB_*.csv"))
        if replay:
            name = st.selectbox("Replay a log through the calibrated model", replay, key=f"replay_{cell_id}")
            log = Log.read(VALIDATION_DIR / name)
            f = cached_eval(cell_id, cal["chamber_h_eff_w_m2k"], cal.get("rig_c_th_j_k"), name)
            st.caption(("Used in the fit." if Path(name).stem in [Path(x).stem for x in cal["fit_logs"]]
                        else "**Hold-out** — not used in the fit.")
                       + f" V RMSE {f.v_rmse_op_mv:.0f} mV (SOC ≥ 10 %), {f.v_rmse_mv:.0f} mV (all) · "
                         f"T RMSE {f.t_rmse_k:.2f} K · core runs up to {f.core_gap_k:.1f} K above the surface "
                         "(not modelled)")
            c1, c2 = st.columns(2)
            c1.plotly_chart(figures.validation(log.t_s, log.voltage_v, f.v_pred, "Terminal voltage [V]"),
                            width="stretch")
            c2.plotly_chart(figures.validation(log.t_s, log.temp_c, f.t_pred, "Surface temperature [°C]"),
                            width="stretch")

    st.subheader("Fit your own log")
    st.caption("Replays a measured current log through the same simulator and fits R0, R1, τ, capacity and h_eff. "
               "CSV columns: time_s, current_a (+ = discharge), voltage_v, temp_c. Drop logs in data/validation/.")
    logs = sorted(p.name for p in VALIDATION_DIR.glob("*.csv"))
    cells = sorted(p.stem for p in CELL_DIR.glob("*.json"))
    if not logs:
        st.info("No logs in data/validation/ yet.")
    else:
        c1, c2 = st.columns(2)
        log_name = c1.selectbox("Log", logs)
        cell_id = c2.selectbox("Start from cell", cells, index=cells.index("nmc21700_5ah_uncalibrated")
                               if "nmc21700_5ah_uncalibrated" in cells else 0)
        if log_name.startswith("SYNTHETIC"):
            st.warning("This log is SYNTHETIC (generated by our own model + noise). It checks that the fitting "
                       "method recovers known parameters — it is **not** validation evidence.")
        if st.button("Fit model to log"):
            res = cached_fit(log_name, cell_id)
            m1, m2 = st.columns(2)
            m1.metric("Voltage RMSE", f"{res.v_rmse_mv:.1f} mV")
            m2.metric("Temperature RMSE", f"{res.t_rmse_k:.2f} K")
            st.dataframe(pd.DataFrame({"parameter": list(res.fitted), "start": res.initial.values(),
                                       "fitted": res.fitted.values()}), hide_index=True)
            log = Log.read(VALIDATION_DIR / log_name)
            st.plotly_chart(figures.validation(log.t_s, log.voltage_v, res.v_pred, "Terminal voltage [V]"),
                            width="stretch")
            st.plotly_chart(figures.validation(log.t_s, log.temp_c, res.t_pred, "Cell temperature [°C]"),
                            width="stretch")
            st.caption("Save fitted parameters as a new cell: "
                       f"`python -m packforge.fit data/validation/{log_name} --cell {cell_id} --save`")
