"""Electrical model: S×P sizing, voltage window, usable energy, pack resistance and busbar I²R.

    V_pack = S · V_cell                 capacity = P · C_cell          E_usable = S·P·V_nom·C_cell · DoD
    R_cell = R0 · (1 + BOL_R_MARGIN)    R_cells = S · R_cell / P
    R_busbar = (S + 1) · R_link / P     (S−1 inter-group links + 2 terminal links, P strips in parallel each)
    V_terminal = S · (OCV(soc) − I_cell · R_cell) − I · R_busbar      (I > 0 = discharge)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.models.schemas import BusbarSpec, CellSpec, ModuleDesignInput

BOL_R_MARGIN = 0.15         # A-EL-01: resistance margin for ageing/spread over the datasheet beginning-of-life value
PEAK_DISCHARGE_C = 2.0      # A-EL-02: peak (acceleration) discharge used for protection sizing

# A-EL-03: generic OCV(SoC) shapes per chemistry (class curves, not a specific part; only used for voltage traces)
OCV_TABLES: dict[str, tuple[tuple[float, ...], tuple[float, ...]]] = {
    "NMC": ((0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
            (3.00, 3.45, 3.55, 3.60, 3.65, 3.70, 3.78, 3.87, 3.96, 4.07, 4.20)),
    "LFP": ((0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
            (2.50, 3.15, 3.22, 3.26, 3.28, 3.29, 3.30, 3.31, 3.33, 3.36, 3.65)),
}


def ocv(chemistry: str, soc: np.ndarray | float) -> np.ndarray:
    xs, ys = OCV_TABLES[chemistry]
    return np.interp(soc, xs, ys)


@dataclass(frozen=True)
class PackElectrical:
    n_series: int
    n_parallel: int
    n_cells: int
    v_nom_v: float
    v_min_v: float
    v_max_v: float
    capacity_ah: float
    nominal_energy_kwh: float
    usable_energy_kwh: float
    r_cell_ohm: float
    r_cells_pack_ohm: float
    r_busbar_ohm: float
    peak_discharge_a: float
    busbar_strip_current_a: float

    @property
    def r_pack_ohm(self) -> float:
        return self.r_cells_pack_ohm + self.r_busbar_ohm

    def terminal_voltage(self, chemistry: str, soc: np.ndarray, i_pack_a: np.ndarray,
                         r_cell_ohm: float | None = None) -> np.ndarray:
        r = self.r_cell_ohm if r_cell_ohm is None else r_cell_ohm
        i_cell = i_pack_a / self.n_parallel
        return self.n_series * (ocv(chemistry, soc) - i_cell * r) - i_pack_a * self.r_busbar_ohm


def pack_electrical(design: ModuleDesignInput, cell: CellSpec, busbar: BusbarSpec,
                    r_cell_ohm: float | None = None) -> PackElectrical:
    """`r_cell_ohm` overrides the datasheet R0 (e.g. the PyBaMM effective resistance); the margin applies to both."""
    s, p = design.n_series, design.n_parallel
    r_cell = (cell.r0_ohm if r_cell_ohm is None else r_cell_ohm) * (1 + BOL_R_MARGIN)
    nominal_kwh = s * p * cell.energy_wh / 1000
    peak = PEAK_DISCHARGE_C * p * cell.capacity_ah
    return PackElectrical(
        n_series=s, n_parallel=p, n_cells=s * p,
        v_nom_v=s * cell.v_nom_v, v_min_v=s * cell.v_min_v, v_max_v=s * cell.v_max_v,
        capacity_ah=p * cell.capacity_ah,
        nominal_energy_kwh=nominal_kwh,
        usable_energy_kwh=nominal_kwh * design.usable_dod,
        r_cell_ohm=r_cell,
        r_cells_pack_ohm=s * r_cell / p,
        r_busbar_ohm=(s + 1) * busbar.link_resistance_ohm / p,
        peak_discharge_a=peak,
        busbar_strip_current_a=peak / p,
    )
