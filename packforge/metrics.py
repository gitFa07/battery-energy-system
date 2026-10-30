"""KPIs from static calculations and simulation traces, each tagged with its evidence level."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .schema import Design, Evidence, Subsystem
from .sim import Trace


@dataclass(frozen=True)
class MetricMeta:
    label: str
    unit: str
    evidence: Evidence
    model: str
    subsystems: tuple[Subsystem, ...]


METRICS: dict[str, MetricMeta] = {
    "v_nom": MetricMeta("Nominal voltage", "V", "calculated", "static: S x V_nom", ("cell", "electrical")),
    "energy_nominal_wh": MetricMeta("Nominal energy", "Wh", "calculated", "static", ("cell", "electrical")),
    "usable_energy_wh": MetricMeta("Usable energy (drive)", "Wh", "simulated", "sim: drive",
                                   ("cell", "electrical", "thermal", "protection")),
    "drive_time_min": MetricMeta("Drive time to cutoff", "min", "simulated", "sim: drive",
                                 ("cell", "electrical", "protection")),
    "charge_time_min": MetricMeta("Charge time (plug-in → 80%)", "min", "simulated",
                                  "sim: charge after the drive, incl. thermal hold",
                                  ("cell", "thermal", "control", "sensing")),
    "thermal_hold_min": MetricMeta("Thermal hold after plug-in", "min", "simulated", "sim: charge after the drive",
                                   ("thermal", "control", "sensing")),
    "charge_time_10_80_min": MetricMeta("Charge time 10-80%", "min", "simulated", "sim: charge, excl. hold",
                                        ("cell", "thermal", "control", "sensing")),
    "charge_time_full_min": MetricMeta("Charge time to CV end", "min", "simulated", "sim: charge",
                                       ("cell", "thermal", "control")),
    "charge_time_bound_min": MetricMeta("Thermal-limit charge bound 10-80%", "min", "calculated",
                                        "hand calc: interior cell, full current to its limit, then held there",
                                        ("cell", "thermal")),
    "t_max_charge_c": MetricMeta("Peak cell temp (charge)", "°C", "simulated", "sim: charge",
                                 ("cell", "thermal", "control")),
    "t_max_drive_c": MetricMeta("Peak cell temp (drive)", "°C", "simulated", "sim: drive", ("cell", "thermal")),
    "delta_t_c": MetricMeta("Max cell-to-cell ΔT", "K", "simulated", "sim: both", ("thermal",)),
    "sensor_blind_spot_c": MetricMeta("Hottest cell minus BMS hotspot view", "K", "simulated", "sim: both",
                                      ("sensing", "thermal", "control")),
    "heat_w_charge": MetricMeta("Mean cell heat (charge)", "W", "simulated", "sim: charge", ("cell", "thermal")),
    "peak_cell_current_a": MetricMeta("Peak cell current (drive)", "A", "simulated", "sim: drive",
                                      ("cell", "electrical")),
    "peak_pack_current_a": MetricMeta("Peak pack current (drive)", "A", "simulated", "sim: drive",
                                      ("electrical",)),
    "cycle_life_est": MetricMeta("Est. cycle life to 80%", "cycles", "estimated",
                                 "datasheet life x Arrhenius(mean T)", ("cell", "thermal")),
    "mass_kg": MetricMeta("Pack mass", "kg", "calculated", "BOM sum", ("mechanical", "thermal")),
    "volume_l": MetricMeta("Pack volume", "L", "calculated", "cell volume / packing x overhead",
                           ("mechanical", "thermal")),
    "cost_inr": MetricMeta("Pack cost", "₹", "calculated", "BOM sum", ("cost",)),
    "cost_per_kwh_inr": MetricMeta("Cost per usable kWh", "₹/kWh", "calculated", "cost / usable energy", ("cost",)),
    "cells_per_temp_sensor": MetricMeta("Cells per temp sensor", "cells", "calculated", "static", ("sensing",)),
}


# default KPI order for tables (CLI, UI, report)
KPIS = ["v_nom", "usable_energy_wh", "charge_time_min", "thermal_hold_min", "charge_time_10_80_min",
        "charge_time_bound_min", "t_max_charge_c",
        "t_max_drive_c", "delta_t_c", "sensor_blind_spot_c", "peak_cell_current_a", "mass_kg", "volume_l", "cost_inr",
        "cost_per_kwh_inr", "cycle_life_est"]


def charge_time_bound_min(d: Design, ambient_c: float) -> float:
    """Ideal thermally limited 10->80 % charge of an interior cell from ambient (independent cross-check of the sim).

    Phase 1 — full current I until the cell reaches its charge limit (first-order lump, C = m·cp, G = h·A, no
    neighbour help):  t1 = -(C/G)·ln(1 - ΔT_lim/ΔT_ss),  ΔT_ss = I²R/G   (G -> 0:  t1 = C·ΔT_lim / I²R).
    Phase 2 — the current that holds it at the limit:  I_h = sqrt(G·ΔT_lim / R(T_lim)).
    Q = 0.7·capacity; R = (R0 + tab + R1)·Arrhenius·heat_factor. A real BMS sees only its sensors and starts
    derating below the limit, so the sim should not beat this.
    """
    c = d.cell
    dtemp = c.t_charge_max_c - ambient_c
    if dtemp <= 0:
        return float("nan")
    q = 0.7 * c.capacity_ah * 3600
    r = lambda t_c: ((c.r0_ohm + d.interconnect.cell_tab_resistance_ohm + c.r1_ohm) * c.heat_factor  # noqa: E731
                     * np.exp(c.r_temp_k * (1 / (t_c + 273.15) - 1 / 298.15)))
    heat_cap, g = c.mass_kg * c.cp_j_kgk, d.cooling.h_eff_w_m2k * c.surface_m2
    current = min(c.max_charge_a, d.control.charge_c_rate * c.capacity_ah)
    heat = current ** 2 * r(ambient_c + dtemp / 2)
    if g <= 0:
        t1 = heat_cap * dtemp / heat
    elif heat <= g * dtemp:
        return q / current / 60  # never reaches the limit at full current
    else:
        t1 = -heat_cap / g * np.log(1 - g * dtemp / heat)
    if current * t1 >= q:
        return q / current / 60
    if g <= 0:
        return float("inf")
    hold = np.sqrt(g * dtemp / r(c.t_charge_max_c))
    return (t1 + (q - current * t1) / hold) / 60


def static_metrics(d: Design) -> dict[str, float]:
    c, n = d.cell, d.n_cells
    mass = (n * (c.mass_kg + d.mechanical.holder_busbar_mass_per_cell_kg) + d.mechanical.enclosure_mass_kg
            + d.bms.mass_kg + d.cooling.mass_kg)
    volume = n * c.volume_l / d.mechanical.packing_fraction * d.mechanical.volume_overhead_factor + d.cooling.volume_l
    cost = (n * (c.cost_inr + d.costs.holder_busbar_per_cell_inr + d.costs.assembly_per_cell_inr)
            + d.costs.enclosure_inr + d.bms.cost_inr + d.cooling.cost_inr
            + d.sensing.n_temp_sensors * d.sensing.sensor_cost_inr)
    return {
        "v_nom": d.topology.series * c.v_nom,
        "energy_nominal_wh": n * c.capacity_ah * c.v_nom,
        "mass_kg": mass,
        "volume_l": volume,
        "cost_inr": cost,
        "cells_per_temp_sensor": n / d.sensing.n_temp_sensors,
    }


def _nanmax(x: np.ndarray) -> float:
    return float(np.nanmax(x)) if np.isfinite(x).any() else float("nan")


def _first_time(t: np.ndarray, series: np.ndarray, threshold: float) -> float:
    hit = np.flatnonzero(series >= threshold)
    return float(t[hit[0]]) if hit.size else float("nan")


def trace_metrics(d: Design, charge: Trace, drive: Trace, sample: int = 0) -> dict[str, float]:
    i = sample
    ce, de = charge.end_step[i], drive.end_step[i]
    ct, dtr = charge.t_s[:ce], drive.t_s[:de]
    dt = float(drive.t_s[1] - drive.t_s[0]) if drive.t_s.size > 1 else 1.0
    t10 = _first_time(ct, charge.soc_mean[:ce, i], 0.10 + 1e-9) if charge.soc_mean[0, i] < 0.1 else 0.0
    t80 = _first_time(ct, charge.soc_mean[:ce, i], 0.80)
    full = float(ct[-1] + dt) if charge.end_reason[i] == "CV complete" else float("nan")
    energy = float(np.nansum(drive.v_pack[:de, i] * drive.current_a[:de, i]) * dt / 3600)
    flowing = charge.current_a[:ce, i] < 0  # thermal hold before charging is not "charging temperature"
    hold = float(ct[np.argmax(flowing)]) if flowing.any() else float("nan")
    mean_t = np.concatenate([charge.t_mean[:ce, i], drive.t_mean[:de, i]])
    aging = np.exp(d.cell.aging_ea_over_r_k * (1 / 298.15 - 1 / (np.nanmean(mean_t) + 273.15)))
    return {
        "usable_energy_wh": energy,
        "drive_time_min": float(dtr[-1] + dt) / 60 if dtr.size else 0.0,
        "charge_time_min": t80 / 60,
        "thermal_hold_min": hold / 60,
        "charge_time_10_80_min": (t80 - t10) / 60,
        "charge_time_full_min": full / 60,
        "t_max_charge_c": _nanmax(charge.t_max[:ce, i][flowing]),
        "t_max_drive_c": _nanmax(drive.t_max[:de, i]),
        "delta_t_c": max(_nanmax(charge.t_max[:ce, i] - charge.t_min[:ce, i]),
                         _nanmax(drive.t_max[:de, i] - drive.t_min[:de, i])),
        "sensor_blind_spot_c": max(_nanmax(charge.t_max[:ce, i] - charge.t_bms_hot[:ce, i]),
                                   _nanmax(drive.t_max[:de, i] - drive.t_bms_hot[:de, i])),
        "heat_w_charge": float(np.nanmean(charge.heat_w_mean[:ce, i][flowing])) if flowing.any() else float("nan"),
        "peak_cell_current_a": _nanmax(drive.cell_current_max[:de, i]),
        "peak_pack_current_a": _nanmax(drive.current_a[:de, i]),
        "cycle_life_est": d.cell.cycle_life_ref / aging,
    }


def all_metrics(d: Design, charge: Trace, drive: Trace, ambient_c: float, sample: int = 0) -> dict[str, float]:
    m = static_metrics(d) | trace_metrics(d, charge, drive, sample)
    m["charge_time_bound_min"] = charge_time_bound_min(d, ambient_c)
    m["cost_per_kwh_inr"] = m["cost_inr"] / max(m["usable_energy_wh"], 1e-9) * 1000
    return m


def fmt(metric: str, value: float) -> str:
    if value is None or np.isnan(value):
        return "n/a"
    unit = METRICS[metric].unit if metric in METRICS else ""
    if abs(value) >= 1000:
        return f"{value:,.0f} {unit}".strip()
    return f"{value:.1f} {unit}".strip() if abs(value) >= 10 else f"{value:.2f} {unit}".strip()
