"""VoltTwin Studio — Streamlit workbench. Renders only; logic lives in src.pipeline / src.physics / src.validator.

Run from the repo root:  .venv/Scripts/streamlit run src/workbench/app.py
"""

from __future__ import annotations

import streamlit as st

from src.config import AMBIENT_REF_C, REQUIREMENTS
from src.models.db import DatasheetDB
from src.models.schemas import ModuleDesignInput
from src.physics.pybamm_runner import run_cell
from src.physics.replay import real_logs, replay_log
from src.pipeline import ROBUSTNESS_FACTORS, StudyEvaluation, evaluate, robustness
from src.workbench import plots, views

st.set_page_config(page_title="VoltTwin Studio", page_icon=":material/battery_charging_full:", layout="wide")
SEVERITY_ICON = {"CRITICAL": ":material/error:", "WARNING": ":material/warning:", "PASS": ":material/check:"}


@st.cache_resource
def get_db() -> DatasheetDB:
    return DatasheetDB()


@st.cache_data(show_spinner="Simulating designs…")
def run_study(designs_json: tuple[str, ...], use_pybamm: bool, heat_factor: float) -> StudyEvaluation:
    designs = [ModuleDesignInput.model_validate_json(j) for j in designs_json]
    return evaluate(designs, get_db(), use_pybamm, heat_factor)


@st.cache_data(show_spinner="Re-running at higher cell heat…")
def run_robustness(designs_json: tuple[str, ...]) -> dict[float, dict[str, str]]:
    return robustness([ModuleDesignInput.model_validate_json(j) for j in designs_json], get_db())


@st.cache_data(show_spinner="Solving PyBaMM SPMe…")
def cell_curve(cell_json: str, c_rate: float, ambient_c: float, use_pybamm: bool):
    from src.models.schemas import CellSpec
    return run_cell(CellSpec.model_validate_json(cell_json), c_rate, ambient_c, use_pybamm)


@st.cache_data(show_spinner="Replaying measured log…")
def replay(log_name: str, cell_json: str):
    from src.models.schemas import CellSpec
    path = next(p for p in real_logs() if p.name == log_name)
    return replay_log(path, CellSpec.model_validate_json(cell_json))


db = get_db()
presets = db.get_presets()
cells = {c.id: c for c in db.list_cells()}
cooling = {c.id: c for c in db.list_cooling()}
busbars = {b.id: b for b in db.list_busbars()}
protection = {p.id: p for p in db.list_protection()}
fuses = [p.id for p in protection.values() if p.kind in ("fuse", "pyro_fuse")]
bmss = [p.id for p in protection.values() if p.kind == "bms"]

# ── Sidebar configurator ───────────────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Design configurator")
    preset_by_id = {p.id: p for p in presets}
    base = preset_by_id[st.selectbox("Start from", list(preset_by_id), format_func=lambda k: preset_by_id[k].name)]
    cell_id = st.selectbox("Cell (chemistry)", list(cells), index=list(cells).index(base.cell_id),
                           format_func=lambda k: cells[k].name)
    c1, c2 = st.columns(2)
    n_s = c1.number_input("Series (S)", 1, 30, base.n_series)
    n_p = c2.number_input("Parallel (P)", 1, 30, base.n_parallel)
    c_rate = st.slider("Fast-charge C-rate", 0.3, 2.0, float(base.charge_c_rate), 0.05)
    ambient = st.slider("Ambient (°C)", 20.0, 50.0, float(base.ambient_c), 1.0)
    dod = st.slider("Usable DoD window", 0.70, 1.0, float(base.usable_dod), 0.01)
    cool_id = st.selectbox("Cooling", list(cooling), index=list(cooling).index(base.cooling_id),
                           format_func=lambda k: cooling[k].name)
    bus_id = st.selectbox("Interconnect", list(busbars), index=list(busbars).index(base.busbar_id),
                          format_func=lambda k: busbars[k].name)
    bms_id = st.selectbox("BMS", bmss, index=bmss.index(base.bms_id), format_func=lambda k: protection[k].name)
    fuse_id = st.selectbox("Fuse", fuses, index=fuses.index(base.fuse_id), format_func=lambda k: protection[k].name)
    n_ntc = st.number_input("NTC sensors", 0, 16, base.n_ntc)
    st.divider()
    use_pybamm = st.toggle("Live PyBaMM SPMe cell model", value=False,
                           help="Cell heat from PyBaMM SPMe (reference cell scaled to this capacity) instead of "
                                "datasheet R0. ~1–7 s per chemistry on first run.")
    heat_factor = st.slider("Cell heat factor (robustness)", 1.0, 3.0, 1.0, 0.25,
                            help="Real-log replays show the datasheet cell model under-predicts the temperature "
                                 "rise 2–4×; raise this to see which verdicts survive.")

custom = ModuleDesignInput(
    id="custom", name="Custom design", cell_id=cell_id, n_series=int(n_s), n_parallel=int(n_p), cooling_id=cool_id,
    busbar_id=bus_id, n_ntc=int(n_ntc), fuse_id=fuse_id, bms_id=bms_id, usable_dod=dod, charge_c_rate=c_rate,
    ambient_c=ambient, source=f"workbench configurator, started from {base.id}")
is_custom = custom.model_dump(exclude={"id", "name", "source"}) != base.model_dump(exclude={"id", "name", "source"})
designs = presets + ([custom] if is_custom else [])
study = run_study(tuple(d.model_dump_json() for d in designs), use_pybamm, heat_factor)
colors = plots.design_colors(study)
focus = study.by_id("custom" if is_custom else base.id)

# ── Header with requirement badges ─────────────────────────────────────────────────────────────────────────────
st.title("VoltTwin Studio")
st.caption(f"48 V e-scooter pack · {AMBIENT_REF_C:g} °C ambient · ride then fast charge 10 → 80 % · "
           f"engine: {focus.run.result.engine}"
           + (f" · cell heat × {heat_factor:g}" if heat_factor != 1 else ""))
st.markdown(f"**{focus.run.design.name}** — verdict **{focus.ranked.verdict}**"
            + (f": {'; '.join(focus.ranked.reasons)}" if focus.ranked.reasons else ""))
badge_cols = st.columns(len(REQUIREMENTS))
for col, req in zip(badge_cols, REQUIREMENTS):
    status = focus.run.result.requirement_status[req.id]
    value = float(getattr(focus.run.result, req.metric))
    with col:
        st.badge(f"{req.id} FAIL" if status == "FAIL" else req.id, color="orange" if status == "FAIL" else "gray",
                 icon=":material/error:" if status == "FAIL" else ":material/check:")
        st.caption(f"{req.text}: {value:.2f} {req.unit}")
for note in focus.run.result.notes:
    st.info(note, icon=":material/info:")

tab_cmp, tab_phys, tab_conf, tab_trace = st.tabs(
    ["3-way comparison & trade-offs", "Multi-physics & PyBaMM", "Conflicts & safety", "Traceability & validation"])

# ── Tab 1: comparison ──────────────────────────────────────────────────────────────────────────────────────────
with tab_cmp:
    rec = study.recommended
    if rec:
        st.success(f"Recommended: **{rec.run.design.name}** (TOPSIS closeness {rec.ranked.closeness:.2f})",
                   icon=":material/recommend:")
    else:
        st.error("No design meets every requirement without a critical conflict.", icon=":material/error:")
    left, right = st.columns([1, 1])
    left.plotly_chart(plots.radar(study), width="stretch")
    right.dataframe(views.ranking_table(study), hide_index=True, width="stretch")
    rob = run_robustness(tuple(d.model_dump_json() for d in designs))
    right.markdown("**Robustness: verdict if real cells make more heat than the datasheet model**")
    right.dataframe(views.robustness_table(rob, {ev.id: ev.run.design.name.split(" (")[0] for ev in study.designs}),
                    hide_index=True, width="stretch")
    right.caption(f"Replays of measured LG M50LT logs (Traceability tab) show the datasheet model under-predicts "
                  f"the temperature rise 2–4×. Factors {', '.join(f'×{f:g}' for f in ROBUSTNESS_FACTORS)}.")
    st.subheader("Requirements")
    st.dataframe(views.requirement_grid(study), hide_index=True, width="stretch")
    st.subheader("Simulated vs Round-1 targets")
    st.dataframe(views.comparison_matrix(study), hide_index=True, width="stretch")
    gaps = views.target_gaps(study)
    if not gaps.empty:
        with st.expander("Where the model and the Round-1 numbers disagree"):
            st.dataframe(gaps[gaps["Within"] == "NO"], hide_index=True, width="stretch")
            st.caption("Round-1 values are submission targets, not measurements; tolerance ±10 % / ±3 K.")

# ── Tab 2: physics ─────────────────────────────────────────────────────────────────────────────────────────────
with tab_phys:
    ids = [ev.id for ev in study.designs]
    pick = study.by_id(st.selectbox("Design", ids, index=ids.index(focus.id),
                                    format_func=lambda k: study.by_id(k).run.design.name, key="phys_design"))
    st.plotly_chart(plots.transient(pick, colors[pick.id]), width="stretch")
    r = pick.run.result
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Plug-in temperature", f"{r.t_charge_start_c:.1f} °C")
    m2.metric("Peak, no derating", f"{r.t_peak_c:.1f} °C")
    m3.metric("Peak, BMS derating", f"{r.t_peak_derated_c:.1f} °C")
    m4.metric("10–80 % with derating", f"{r.charge_time_derated_min:.0f} min",
              delta=f"{r.charge_time_derated_min - r.charge_time_10_80_min:+.0f} min vs nominal", delta_color="inverse")
    st.plotly_chart(plots.heat_breakdown(study), width="stretch")
    st.subheader("Cell electrochemistry")
    show_pb = st.toggle("Solve PyBaMM SPMe for each chemistry", value=use_pybamm, key="pb_curves")
    curves = {}
    for ev in study.designs:
        cell = cells[ev.run.design.cell_id]
        key = f"{cell.chemistry} @ {ev.run.design.charge_c_rate:g} C"
        if key not in curves:
            curves[key] = cell_curve(cell.model_dump_json(), ev.run.design.charge_c_rate, ev.run.design.ambient_c,
                                     show_pb)
    curve_colors = {k: plots.DESIGN_COLORS[i % len(plots.DESIGN_COLORS)] for i, k in enumerate(curves)}
    st.plotly_chart(plots.cell_curves(curves, curve_colors), width="stretch")
    st.caption("PyBaMM reference cells (Marquis2019 NMC, Prada2013 LFP) are not our cells: their heat is scaled by "
               "capacity and used as a cross-check of the datasheet resistance. "
               + " · ".join(f"{k}: R_eff = {ec.r_ratio_vs_datasheet:.2f} × R0" for k, ec in curves.items()))

# ── Tab 3: conflicts ───────────────────────────────────────────────────────────────────────────────────────────
with tab_conf:
    st.caption("Rule families: thermal ↔ electrical (CF-TE), electrical ↔ mechanical (CF-EM), protection & "
               "sensing (CF-PS). CRITICAL disqualifies; a CRITICAL safety alert makes the design UNSAFE.")
    for ev in study.designs:
        active = [a for a in ev.alerts if a.severity != "PASS"]
        with st.expander(f"{ev.run.design.name} — {ev.ranked.verdict} · {len(active)} conflict(s)",
                         expanded=ev.id == focus.id):
            if not active:
                st.write("No conflicts.")
            for a in active:
                st.markdown(f"{SEVERITY_ICON[a.severity]} **{a.severity}{' · safety' if a.safety else ''}** "
                            f"`{a.rule_id}` {a.title} — {a.detail}")
                st.caption(f"Subsystems: {', '.join(a.subsystems)} · threatens: {', '.join(a.requirements) or '—'}"
                           f" · fixes: {'; '.join(a.fixes)}")

# ── Tab 4: traceability & validation ───────────────────────────────────────────────────────────────────────────
with tab_trace:
    ids = [ev.id for ev in study.designs]
    pick_t = study.by_id(st.selectbox("Design", ids, index=ids.index(focus.id),
                                      format_func=lambda k: study.by_id(k).run.design.name, key="trace_design"))
    st.subheader("Requirement → datasheet → model → metric → validation")
    st.dataframe(views.traceability_table(pick_t), hide_index=True, width="stretch")
    with st.expander("Assumptions register"):
        st.dataframe(views.assumptions_table(), hide_index=True, width="stretch")

    st.subheader("Validation against measured data")
    st.caption("TU Berlin LG M50LT internal-temperature dataset (CC BY 4.0) — a proxy for the generic NMC class "
               "cell. VoltTwin's cell is not fitted to it; chamber h and rig heat capacity are test-rig parameters "
               "from the PackForge calibration (25/35 °C), so 45 °C logs are hold-out. The LFP cell has no "
               "measured data and is not validated.")
    nmc = cells["nmc21700_4p8ah"]
    logs = [p.name for p in real_logs()]
    default = next((i for i, n in enumerate(logs) if "CHG" in n and "45C" in n), 0)
    log = st.selectbox("Measured log", logs, index=default)
    st.plotly_chart(plots.validation_overlay(replay(log, nmc.model_dump_json())), width="stretch")
    st.dataframe(views.replay_table([replay(n, nmc.model_dump_json()) for n in logs]), hide_index=True,
                 width="stretch")
