"""Traceability chain per requirement: datasheet parameters → physics model (+ assumptions) → simulated metric
→ validation reference, with the evidence level the metric actually has."""

from __future__ import annotations

from src.config import REQUIREMENTS
from src.models.schemas import Evidence, HardRequirement, TraceabilityRecord
from src.physics.simulate import SimulationRun

# requirement id → (spec fields, physics model, assumptions, evidence, validation reference)
CHAIN: dict[str, tuple[list[str], str, list[str], Evidence, str]] = {
    "REQ-EL-01": (["cell.v_nom_v", "design.n_series"], "electrical.pack_electrical: V = S · V_cell", [],
                  "calculated", "hand calc: tests/test_physics_engine.py::test_electrical_hand_calc"),
    "REQ-EL-02": (["cell.v_nom_v", "cell.capacity_ah", "design.n_series", "design.n_parallel", "design.usable_dod"],
                  "electrical.pack_electrical: E = S·P·V·C·DoD", ["A-EL-04", "A-CL-01"], "calculated",
                  "hand calc: tests/test_physics_engine.py::test_electrical_hand_calc"),
    "REQ-TH-01": (["cell.r0_ohm", "cell.mass_kg", "cell.cp_j_kgk", "cooling.r_th_k_w", "cooling.pcm_mass_kg",
                   "cooling.pcm_latent_j_kg", "cooling.pcm_melt_c", "busbar.resistivity_ohm_m",
                   "design.charge_c_rate", "design.ambient_c"],
                  "thermal.simulate_cycle: lumped enthalpy node, ride + charge, no derating",
                  ["A-EL-01", "A-TH-01", "A-TH-02", "A-TH-03", "A-TH-04", "A-TH-05", "A-CL-01"], "simulated",
                  "energy balance + dt convergence tests; PyBaMM SPMe heat cross-check. Not validated against "
                  "measured pack temperatures."),
    "REQ-CH-01": (["design.charge_c_rate", "cell.capacity_ah", "cooling.r_th_k_w", "cell.r0_ohm"],
                  "thermal.simulate_cycle with BMS derating", ["A-TH-04", "A-TH-06", "A-EL-01"], "simulated",
                  "derating test (tests/test_physics_engine.py); no measured charge log for these cells."),
    "REQ-ME-01": (["cell.mass_kg", "busbar.mass_per_cell_kg", "cooling.mass_kg", "bms.mass_kg", "fuse.mass_kg"],
                  "mechanical_bom.pack_mechanical: mass sum", ["A-ME-01", "A-ME-02"], "calculated",
                  "BOM sum test; no weighed prototype."),
    "REQ-ME-02": (["cell.diameter_mm", "cell.height_mm", "cooling.volume_l", "design.n_series", "design.n_parallel"],
                  "mechanical_bom.pack_mechanical: packing + enclosure overhead", ["A-ME-01", "A-ME-02"], "calculated",
                  "packing-fraction hand calc; no CAD/prototype."),
    "REQ-EC-01": (["cell.cost_usd", "busbar.cost_per_cell_usd", "cooling.cost_usd", "bms.cost_usd", "fuse.cost_usd"],
                  "mechanical_bom.pack_mechanical: itemised BOM", ["A-EC-01"], "estimated",
                  "class-estimate part costs; no supplier quotes."),
}


def _resolve(field: str, run: SimulationRun) -> str:
    """'cell.r0_ohm' → 'nmc21700_4p8ah.r0_ohm' using the design's spec ids."""
    d = run.design
    owner, name = field.split(".", 1)
    ids = {"cell": d.cell_id, "cooling": d.cooling_id, "busbar": d.busbar_id, "bms": d.bms_id, "fuse": d.fuse_id,
           "design": d.id}
    return f"{ids[owner]}.{name}"


def _limit(req: HardRequirement) -> str:
    if req.min is not None and req.max is not None:
        return f"{req.min:g}–{req.max:g} {req.unit}"
    return f"{'≥' if req.min is not None else '≤'} {req.min if req.min is not None else req.max:g} {req.unit}"


def build_traceability(run: SimulationRun) -> list[TraceabilityRecord]:
    r = run.result
    records = []
    for req in REQUIREMENTS:
        fields, model, assumptions, evidence, ref = CHAIN[req.id]
        if req.id in ("REQ-TH-01", "REQ-CH-01") and r.engine == "pybamm":
            model += f" (cell heat from PyBaMM SPMe, R_eff = {r.r_eff_ratio_vs_datasheet:.2f} × R0)"
        records.append(TraceabilityRecord(
            requirement_id=req.id, datasheet_parameters=[_resolve(f, run) for f in fields], physics_model=model,
            assumptions=assumptions, simulated_metric=req.metric, value=float(getattr(r, req.metric)),
            limit=_limit(req), status=r.requirement_status[req.id], evidence=evidence, validation_reference=ref))
    return records
