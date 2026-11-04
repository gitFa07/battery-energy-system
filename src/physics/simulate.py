"""Coupled simulation of one design: electrochemistry → electrical → thermal (ride + charge, ± BMS derating)
→ mechanical/BOM → requirement status. Subsystems exchange values only through `ModuleDesignInput`, the specs
and the dataclasses returned here.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.config import REQUIREMENTS
from src.models.db import DatasheetDB
from src.models.schemas import ModuleDesignInput, ModuleSimulationResult
from src.physics.electrical import PackElectrical, pack_electrical
from src.physics.mechanical_bom import PackMechanical, pack_mechanical
from src.physics.pybamm_runner import CellElectrochem, run_cell
from src.physics.thermal import Transient, simulate_cycle


@dataclass
class SimulationRun:
    design: ModuleDesignInput
    result: ModuleSimulationResult
    nominal: Transient       # charge at the design rate, no BMS intervention → raw thermal capability
    derated: Transient       # same cycle with BMS derating → real turnaround time
    electrochem: CellElectrochem
    electrical: PackElectrical
    mechanical: PackMechanical


def simulate_design(design: ModuleDesignInput, db: DatasheetDB, use_pybamm: bool = False) -> SimulationRun:
    cell, cooling, busbar = db.get_cell(design.cell_id), db.get_cooling(design.cooling_id), db.get_busbar(design.busbar_id)
    fuse, bms, ntc = db.get_protection(design.fuse_id), db.get_protection(design.bms_id), db.get_protection("ntc_10k")

    ec = run_cell(cell, design.charge_c_rate, design.ambient_c, use_pybamm)
    pe = pack_electrical(design, cell, busbar, r_cell_ohm=ec.r_eff_ohm)
    # PyBaMM's total heat already contains the reversible part
    reversible = ec.engine == "surrogate"
    nominal = simulate_cycle(design, cell, cooling, pe, derate=False, reversible=reversible)
    derated = simulate_cycle(design, cell, cooling, pe, derate=True, reversible=reversible)
    mech = pack_mechanical(design, cell, cooling, busbar, fuse, bms, ntc)

    b = nominal.breakdown_w
    notes = [ec.note] if ec.note else []
    if not derated.charge_complete:
        notes.append("derated charge did not reach 80 % SoC within the time limit")
    result = ModuleSimulationResult(
        design_id=design.id, engine=ec.engine,
        v_nom_v=pe.v_nom_v, v_min_v=pe.v_min_v, v_max_v=pe.v_max_v,
        n_cells=pe.n_cells, capacity_ah=pe.capacity_ah,
        nominal_energy_kwh=pe.nominal_energy_kwh, usable_energy_kwh=pe.usable_energy_kwh,
        r_pack_ohm=pe.r_pack_ohm, r_eff_ratio_vs_datasheet=ec.r_ratio_vs_datasheet,
        peak_discharge_a=pe.peak_discharge_a, busbar_strip_current_a=pe.busbar_strip_current_a,
        t_charge_start_c=float(nominal.t_core_c[nominal.charge()][0]),
        t_peak_c=nominal.t_peak_c, t_peak_derated_c=derated.t_peak_c,
        charge_time_10_80_min=nominal.charge_time_min, charge_time_derated_min=derated.charge_time_min,
        charge_complete=derated.charge_complete,
        heat_gen_w=b["cells_irreversible"] + b["cells_reversible"] + b["busbar"],
        heat_cells_w=b["cells_irreversible"], heat_reversible_w=b["cells_reversible"], heat_busbar_w=b["busbar"],
        heat_reject_w=b["rejected"], heat_pcm_w=b["pcm_latent"],
        mass_kg=mech.mass_kg, volume_l=mech.volume_l, bom_cost_usd=mech.bom_cost_usd,
        notes=notes,
    )
    result.requirement_status = {r.id: r.status(getattr(result, r.metric)) for r in REQUIREMENTS}
    return SimulationRun(design, result, nominal, derated, ec, pe, mech)
