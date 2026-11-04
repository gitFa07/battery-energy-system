"""Cell electrochemistry: PyBaMM SPMe + lumped thermal, with a fast datasheet-ECM surrogate fallback.

PyBaMM mode charges the chemistry's reference cell (Marquis2019 for NMC, Prada2013 for LFP) from 10 to 80 % SoC
at the design C-rate and ambient, and reduces its total heat (irreversible + reversible) to an effective
resistance, scaled to our cell by capacity (same chemistry, same C-rate → R ∝ 1/capacity):
    R_eff = mean(Q_total) / I_ref² · (C_ref / C_cell)
The reference cells are not our cells: this is a physics cross-check of the datasheet R0, not a calibration.
Surrogate mode returns the datasheet R0 with OCV + I·R voltage (no solver, milliseconds).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from src.config import CHARGE_SOC_WINDOW
from src.models.schemas import CellSpec
from src.physics.electrical import ocv

FILL_FROM = "Marquis2019"   # thermal/geometry keys Prada2013 lacks for the lumped thermal model


@dataclass(frozen=True)
class CellElectrochem:
    engine: str               # "pybamm" | "surrogate"
    parameter_set: str
    r_eff_ohm: float          # per our cell, before the BoL margin
    r_ratio_vs_datasheet: float
    soc: np.ndarray           # charge curve (our SoC axis)
    voltage_v: np.ndarray     # cell terminal voltage during the charge
    heat_w: np.ndarray        # per-cell heat during the charge, scaled to our cell
    note: str = ""


def surrogate(cell: CellSpec, c_rate: float, note: str = "") -> CellElectrochem:
    soc = np.linspace(*CHARGE_SOC_WINDOW, 50)
    i = c_rate * cell.capacity_ah
    return CellElectrochem("surrogate", "datasheet ECM", cell.r0_ohm, 1.0, soc,
                           ocv(cell.chemistry, soc) + i * cell.r0_ohm, np.full_like(soc, i**2 * cell.r0_ohm), note)


@lru_cache(maxsize=32)
def _solve(parameter_set: str, c_rate: float, ambient_c: float) -> tuple[float, np.ndarray, np.ndarray, np.ndarray]:
    import pybamm

    pv = pybamm.ParameterValues(parameter_set)
    if parameter_set != FILL_FROM:
        base = pybamm.ParameterValues(FILL_FROM)
        pv.update({k: v for k, v in base.items() if k not in pv.keys()}, check_already_exists=False)
    t_k = ambient_c + 273.15
    pv.update({"Ambient temperature [K]": t_k, "Initial temperature [K]": t_k})
    cap = float(pv["Nominal cell capacity [A.h]"])
    lo, hi = CHARGE_SOC_WINDOW
    minutes = (hi - lo) / c_rate * 60
    exp = pybamm.Experiment([f"Charge at {c_rate:g}C for {minutes:.2f} minutes or until "
                             f"{float(pv['Upper voltage cut-off [V]']):.3f} V"], period="20 seconds")
    model = pybamm.lithium_ion.SPMe(options={"thermal": "lumped"})
    sol = pybamm.Simulation(model, parameter_values=pv, experiment=exp).solve(initial_soc=lo)
    t = sol["Time [s]"].entries
    return cap, lo + t * c_rate / 3600, sol["Voltage [V]"].entries, sol["Total heating [W]"].entries


def run_cell(cell: CellSpec, c_rate: float, ambient_c: float, use_pybamm: bool = False) -> CellElectrochem:
    if not use_pybamm:
        return surrogate(cell, c_rate)
    try:
        cap_ref, soc, v, q = _solve(cell.pybamm_parameter_set, round(c_rate, 3), round(ambient_c, 1))
    except Exception as e:  # missing package, solver failure, unknown parameter set → fall back, say why
        return surrogate(cell, c_rate, note=f"PyBaMM unavailable ({type(e).__name__}: {e}); used surrogate")
    i_ref = c_rate * cap_ref
    r_eff = float(np.mean(q)) / i_ref**2 * cap_ref / cell.capacity_ah
    scale = cell.capacity_ah / cap_ref
    return CellElectrochem("pybamm", cell.pybamm_parameter_set, r_eff, r_eff / cell.r0_ohm, soc, v, q * scale,
                           note=f"SPMe reference cell {cap_ref:.2f} Ah scaled to {cell.capacity_ah:g} Ah")
