"""Conflict & limit checker.

Two kinds of checks:
  * requirement checks  — a metric against a requirement in the study (traceable to REQ ids)
  * interface rules     — consistency *between* subsystems and against cell datasheet limits,
                          which is where cross-discipline assumptions usually collide.
Every finding carries the subsystems involved, a cause chain and candidate fixes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from .metrics import METRICS, fmt
from .schema import Design, Study, Subsystem

Severity = Literal["fail", "warn", "pass"]


@dataclass
class Finding:
    id: str
    title: str
    severity: Severity
    subsystems: tuple[Subsystem, ...]
    detail: str
    requirement: str | None = None
    fixes: list[str] = field(default_factory=list)


def _status(ok: bool, critical: bool) -> Severity:
    return "pass" if ok else ("fail" if critical else "warn")


# Cause chains and fixes for requirement metrics, keyed by metric. `m` = metrics, `d` = design.
EXPLAIN = {
    "t_max_charge_c": lambda d, m: (
        f"{d.control.charge_c_rate:g}C charge with {d.cooling.type} cooling (h={d.cooling.h_eff_w_m2k:g} W/m²K); "
        f"BMS derates on {'its hottest NTC' if d.control.derate_on == 'sensed' else 'an observer estimate'} which "
        f"under-reads the hotspot by up to {m['sensor_blind_spot_c']:.1f} K ({d.sensing.n_temp_sensors} NTCs, "
        f"'{d.sensing.placement}') → charging runs while the hottest cell reaches {m['t_max_charge_c']:.1f} °C",
        ["move NTCs to the pack hotspot or derate on a thermal observer (software-only)",
         "improve cooling (conduction plate / forced air)", "lower charge C-rate"]),
    "t_max_drive_c": lambda d, m: (
        f"peak {m['peak_cell_current_a']:.1f} A/cell on the drive cycle → T_max {m['t_max_drive_c']:.1f} °C",
        ["add parallel cells to cut per-cell current", "improve cooling"]),
    "charge_time_min": lambda d, m: (
        f"plug-in after the ride → {m['thermal_hold_min']:.0f} min thermal hold, then {d.control.charge_c_rate:g}C "
        f"nominal with derating from {d.control.derate_start_c:g} °C → 80 % after {m['charge_time_min']:.0f} min",
        ["cool the pack faster (conduction plate / forced air) so the hold ends sooner",
         "raise charge C-rate (check cell limit & temperature)", "use a chemistry with a wider charge window"]),
    "charge_time_10_80_min": lambda d, m: (
        f"{d.control.charge_c_rate:g}C nominal rate, derating from {d.control.derate_start_c:g} °C "
        f"→ {m['charge_time_10_80_min']:.0f} min",
        ["raise charge C-rate (check cell limit & temperature)", "improve cooling so derating engages later"]),
    "usable_energy_wh": lambda d, m: (
        f"{d.topology.series}S{d.topology.parallel}P of {d.cell.capacity_ah:g} Ah; weakest series group "
        f"hits UV {d.protection.uv_cell_v:g} V first → {m['usable_energy_wh']:.0f} Wh",
        ["add a parallel cell", "use a higher-capacity cell", "tighten cell matching (capacity σ)"]),
    "delta_t_c": lambda d, m: (
        f"edge cells cool {d.cooling.edge_factor:g}x better than interior cells; neighbour conductance "
        f"{d.cooling.g_neighbor_w_k:g} W/K → ΔT {m['delta_t_c']:.1f} K",
        ["add a heat-spreading plate", "increase cell spacing at the centre"]),
    "sensor_blind_spot_c": lambda d, m: (
        f"{d.sensing.n_temp_sensors} NTCs placed '{d.sensing.placement}' → BMS under-reads hottest cell by "
        f"{m['sensor_blind_spot_c']:.1f} K, so derating and OT protection act late",
        ["place an NTC at the thermal centre", "add sensors"]),
    "mass_kg": lambda d, m: (f"{d.n_cells} × {d.cell.mass_kg * 1000:.0f} g cells + structure → {m['mass_kg']:.1f} kg",
                             ["higher energy-density chemistry", "lighter enclosure"]),
    "volume_l": lambda d, m: (f"{d.n_cells} cells at packing {d.mechanical.packing_fraction:g} → {m['volume_l']:.1f} L",
                              ["hex packing", "larger-format cell"]),
    "cycle_life_est": lambda d, m: (
        f"datasheet {d.cell.cycle_life_ref:.0f} cycles at 25 °C, derated for mean operating temperature "
        f"→ {m['cycle_life_est']:.0f} cycles", ["lower operating temperature", "longer-life chemistry (LFP)"]),
}


def requirement_checks(d: Design, study: Study, m: dict[str, float]) -> list[Finding]:
    out = []
    for req in study.requirements:
        val = m.get(req.metric, float("nan"))
        ok = not math.isnan(val) and (req.min is None or val >= req.min) and (req.max is None or val <= req.max)
        bound = " – ".join(x for x in (
            f"≥ {req.min:g}" if req.min is not None else "", f"≤ {req.max:g}" if req.max is not None else "") if x)
        why, fixes = EXPLAIN.get(req.metric, lambda *_: ("", []))(d, m)
        meta = METRICS.get(req.metric)
        out.append(Finding(
            id=req.id, title=req.text, severity=_status(ok, req.priority == "must"),
            subsystems=meta.subsystems if meta else (), requirement=req.id,
            detail=f"{fmt(req.metric, val)} (required {bound} {req.unit})" + (f" — {why}" if why and not ok else ""),
            fixes=[] if ok else fixes))
    return out


def interface_checks(d: Design, m: dict[str, float], charge_events: list[str]) -> list[Finding]:
    c, p, ctrl, ic = d.cell, d.protection, d.control, d.interconnect
    i_chg_cell = ctrl.charge_c_rate * c.capacity_ah
    peak = m["peak_pack_current_a"]
    rules = [
        ("IF-01", "Charge current within cell limit", ("cell", "control"), i_chg_cell <= c.max_charge_a, True,
         f"{i_chg_cell:.1f} A/cell vs datasheet {c.max_charge_a:g} A", ["lower charge C-rate", "add parallel cells"]),
        ("IF-02", "Drive current within cell limit", ("cell", "electrical"), m["peak_cell_current_a"] <= c.max_discharge_a,
         True, f"{m['peak_cell_current_a']:.1f} A/cell vs datasheet {c.max_discharge_a:g} A",
         ["add parallel cells", "limit motor peak power"]),
        ("IF-03", "Fuse does not nuisance-trip at peak", ("electrical", "protection"), ic.fuse_rating_a >= 1.25 * peak,
         False, f"fuse {ic.fuse_rating_a:g} A vs 1.25 × peak {peak:.0f} A", ["raise fuse rating (keep below busbar ampacity)"]),
        ("IF-04", "Fuse protects busbar", ("electrical", "protection"), ic.fuse_rating_a <= ic.busbar_ampacity_a, True,
         f"fuse {ic.fuse_rating_a:g} A vs busbar {ic.busbar_ampacity_a:g} A", ["lower fuse rating", "thicker busbar"]),
        ("IF-05", "Busbar carries peak current", ("electrical", "mechanical"), ic.busbar_ampacity_a >= peak, True,
         f"busbar {ic.busbar_ampacity_a:g} A vs peak {peak:.0f} A", ["thicker / wider busbar"]),
        ("IF-06", "BMS supports series count", ("sensing", "electrical"), d.topology.series <= d.bms.max_series, True,
         f"{d.topology.series}S vs BMS max {d.bms.max_series}S", ["choose a BMS AFE with more channels"]),
        ("IF-07", "OV threshold within cell rating", ("protection", "cell"), p.ov_cell_v <= c.v_max + 0.05, True,
         f"OV {p.ov_cell_v:g} V vs cell max {c.v_max:g} V", ["set OV ≤ cell V_max + 50 mV"]),
        ("IF-08", "UV threshold within cell rating", ("protection", "cell"), p.uv_cell_v >= c.v_min, True,
         f"UV {p.uv_cell_v:g} V vs cell min {c.v_min:g} V", ["set UV ≥ cell V_min"]),
        ("IF-09", "Charge OT threshold within cell window", ("protection", "cell"), p.ot_charge_c <= c.t_charge_max_c,
         True, f"OT(charge) {p.ot_charge_c:g} °C vs cell {c.t_charge_max_c:g} °C", ["lower OT(charge) threshold"]),
        ("IF-10", "Discharge OT threshold within cell window", ("protection", "cell"),
         p.ot_discharge_c <= c.t_discharge_max_c, True,
         f"OT(discharge) {p.ot_discharge_c:g} °C vs cell {c.t_discharge_max_c:g} °C", ["lower OT(discharge) threshold"]),
        ("IF-11", "Charger CV below OV protection", ("control", "protection"), ctrl.cv_v_cell < p.ov_cell_v, True,
         f"CV {ctrl.cv_v_cell:g} V vs OV {p.ov_cell_v:g} V — charger would fight protection", ["lower CV setpoint"]),
        ("IF-12", "Derating completes before OT trip", ("control", "protection"), ctrl.derate_end_c <= p.ot_charge_c,
         False, f"derating ends {ctrl.derate_end_c:g} °C vs OT {p.ot_charge_c:g} °C",
         ["end derating at or below the OT(charge) threshold"]),
        ("IF-13", "Over-current limit above drive peak", ("protection", "electrical"), p.oc_discharge_a >= peak, True,
         f"OC {p.oc_discharge_a:g} A vs drive peak {peak:.0f} A — would trip in normal use", ["raise OC limit"]),
        ("IF-14", "Charge completes without protection trip", ("control", "protection", "thermal"),
         not any("trip" in e for e in charge_events), True, "; ".join(charge_events) or "no events",
         ["coordinate derating, sensing placement and OT threshold"]),
    ]
    return [Finding(id=i, title=t, severity=_status(ok, crit), subsystems=sub, detail=det, fixes=[] if ok else fx)
            for i, t, sub, ok, crit, det, fx in rules]


def run_checks(d: Design, study: Study, m: dict[str, float], charge_events: list[str]) -> list[Finding]:
    return requirement_checks(d, study, m) + interface_checks(d, m, charge_events)
