"""Lumped pack thermal model with PCM latent-heat buffer, cell-core hotspot and BMS derating.

One thermal node (all cells + cooling hardware), integrated in enthalpy H [J] so the PCM plateau is exact:
    dH/dt = Q_gen − (T − T_amb) / R_th
    Q_gen = N · (I_cell² · R_cell − I_cell · T_K · dU/dT) + I_pack² · R_busbar      (irreversible + reversible)
    T(H): sensible below the melt point, held at T_melt while the PCM melts, sensible again above.
    T_core = T + q_cell · R_CORE                    (radial core-to-can rise of the hottest cell)
Duty cycle (the e-scooter study): ride at RIDE_C from SOC_RIDE_START down to 10 %, then fast charge 10 → 80 %.
BMS derating scales charge current by clip((T_cutoff − T_sensed) / (T_cutoff − T_derate), 0, 1) on the pack
(NTC) temperature, which lengthens the charge; the nominal run (no derating) gives the design's raw peak.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from src.config import BMS_CUTOFF_C, CHARGE_SOC_WINDOW, T_PEAK_LIMIT_C
from src.models.schemas import CellSpec, CoolingSpec, ModuleDesignInput
from src.physics.electrical import PackElectrical

# Assumptions (ids are referenced by traceability)
ENTROPIC_V_K = {"NMC": -5.0e-5, "LFP": -3.0e-5}  # A-TH-01: class-average dU/dT over 10-80 % SoC; sign varies with SoC
R_CORE_K_W = 3.0            # A-TH-02: 21700 core-to-can radial thermal resistance (typical 2-4 K/W)
CP_ALUMINIUM_J_KGK = 900.0  # A-TH-03: fins/ducts heat capacity
CP_PCM_J_KGK = 2000.0       # A-TH-03: paraffin sensible heat capacity
RIDE_C = 0.5                # A-TH-04: average urban-ride discharge rate before plug-in
SOC_RIDE_START = 0.90       # A-TH-04: ride starts at 90 % SoC and ends at the 10 % charge start
DERATE_START_C = T_PEAK_LIMIT_C   # BMS starts reducing charge current at the requirement limit ...
MAX_CHARGE_S = 6 * 3600     # ... and the derated charge gives up after 6 h
DT_S = 5.0


@dataclass
class Transient:
    """Time series of one ride + charge run. current_a > 0 = discharge (pack level)."""
    t_s: np.ndarray
    phase: np.ndarray        # "ride" | "charge"
    soc: np.ndarray
    current_a: np.ndarray
    voltage_v: np.ndarray
    t_pack_c: np.ndarray
    t_core_c: np.ndarray
    heat_gen_w: np.ndarray
    heat_reject_w: np.ndarray
    pcm_melt_fraction: np.ndarray
    derated: bool
    soc_end: float = 0.0
    breakdown_w: dict[str, float] = field(default_factory=dict)  # mean over the charge phase

    def charge(self) -> np.ndarray:
        return self.phase == "charge"

    @property
    def charge_time_min(self) -> float:
        t = self.t_s[self.charge()]
        return float(t[-1] - t[0]) / 60 + DT_S / 60

    @property
    def t_peak_c(self) -> float:
        return float(self.t_core_c.max())

    @property
    def charge_complete(self) -> bool:
        return bool(self.soc_end >= CHARGE_SOC_WINDOW[1] - 1e-9)


def heat_capacity_j_k(pe: PackElectrical, cell: CellSpec, cooling: CoolingSpec) -> float:
    structure_kg = max(cooling.mass_kg - cooling.pcm_mass_kg, 0.0)
    return (pe.n_cells * cell.mass_kg * cell.cp_j_kgk + structure_kg * CP_ALUMINIUM_J_KGK
            + cooling.pcm_mass_kg * CP_PCM_J_KGK)


def _temperature(h: float, t_ref: float, c: float, t_melt: float | None, e_lat: float) -> tuple[float, float]:
    """Inverse enthalpy → (temperature, PCM melt fraction). H = 0 is the solid PCM at t_ref."""
    if not e_lat or t_melt is None:
        return t_ref + h / c, 0.0
    h_start = c * (t_melt - t_ref)
    if h < h_start:
        return t_ref + h / c, 0.0
    if h < h_start + e_lat:
        return t_melt, (h - h_start) / e_lat
    return t_ref + (h - e_lat) / c, 1.0


def simulate_cycle(design: ModuleDesignInput, cell: CellSpec, cooling: CoolingSpec, pe: PackElectrical,
                   derate: bool, reversible: bool = True, dt: float = DT_S) -> Transient:
    t_amb = design.ambient_c
    c = heat_capacity_j_k(pe, cell, cooling)
    e_lat = cooling.pcm_mass_kg * cooling.pcm_latent_j_kg
    t_melt = cooling.pcm_melt_c
    dudt = ENTROPIC_V_K[cell.chemistry] if reversible else 0.0
    # start in equilibrium with ambient (PCM already molten if ambient is above its melt point)
    h = e_lat if (e_lat and t_melt is not None and t_amb >= t_melt) else 0.0
    temp, melt = _temperature(h, t_amb, c, t_melt, e_lat)

    soc, t = SOC_RIDE_START, 0.0
    rows: list[tuple] = []
    parts = {"cells_irreversible": 0.0, "cells_reversible": 0.0, "busbar": 0.0, "rejected": 0.0, "pcm_latent": 0.0}
    n_charge = 0
    lo, hi = CHARGE_SOC_WINDOW
    phase, t_plug = "ride", 0.0
    while True:
        if phase == "ride" and soc <= lo + 1e-12:
            phase, t_plug = "charge", t
        if phase == "charge" and (soc >= hi - 1e-12 or t - t_plug >= MAX_CHARGE_S):
            break
        if phase == "ride":
            i_cell = RIDE_C * cell.capacity_ah
        else:
            f = float(np.clip((BMS_CUTOFF_C - temp) / (BMS_CUTOFF_C - DERATE_START_C), 0, 1)) if derate else 1.0
            i_cell = -design.charge_c_rate * cell.capacity_ah * f
        i_pack = i_cell * pe.n_parallel
        q_irr = i_cell**2 * pe.r_cell_ohm
        q_rev = -i_cell * (temp + 273.15) * dudt
        q_cell = q_irr + q_rev
        q_bus = i_pack**2 * pe.r_busbar_ohm
        q_gen = pe.n_cells * q_cell + q_bus
        q_rej = (temp - t_amb) / cooling.r_th_k_w
        v = float(pe.terminal_voltage(cell.chemistry, np.array(soc), np.array(i_pack)))
        rows.append((t, phase, soc, i_pack, v, temp, temp + max(q_cell, 0.0) * R_CORE_K_W, q_gen, q_rej, melt))

        h_new = h + (q_gen - q_rej) * dt
        temp_new, melt_new = _temperature(h_new, t_amb, c, t_melt, e_lat)
        if phase == "charge":
            n_charge += 1
            parts["cells_irreversible"] += pe.n_cells * q_irr
            parts["cells_reversible"] += pe.n_cells * q_rev
            parts["busbar"] += q_bus
            parts["rejected"] += q_rej
            parts["pcm_latent"] += (melt_new - melt) * e_lat / dt
        h, temp, melt = h_new, temp_new, melt_new
        soc -= i_cell * dt / 3600 / cell.capacity_ah
        t += dt

    cols = list(zip(*rows))
    tr = Transient(t_s=np.array(cols[0]), phase=np.array(cols[1]), soc=np.array(cols[2]),
                   current_a=np.array(cols[3]), voltage_v=np.array(cols[4]), t_pack_c=np.array(cols[5]),
                   t_core_c=np.array(cols[6]), heat_gen_w=np.array(cols[7]), heat_reject_w=np.array(cols[8]),
                   pcm_melt_fraction=np.array(cols[9]), derated=derate, soc_end=soc)
    tr.breakdown_w = {k: v / max(n_charge, 1) for k, v in parts.items()}
    return tr

