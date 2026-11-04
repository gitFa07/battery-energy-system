"""Cross-disciplinary conflict rules. Each rule reads the simulation result and the specs and returns an alert
with a cause, the subsystems involved, the requirements it threatens, and fixes.

Rule 1  thermal ↔ electrical    T_peak > limit (derating) · Q_gen > cooling capacity · derating stretches charge
Rule 2  electrical ↔ mechanical  cell count × chemistry pushes mass / volume over the envelope
Rule 3  protection & sensing     2 C peak vs fuse and BMS rating · busbar strip ampacity · NTC count on NMC ·
                                 NTCs vs BMS inputs · charge rate vs cell limit
`safety=True` marks alerts that make a design UNSAFE (thermal); other CRITICAL alerts make it REJECTED.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from src.config import T_PEAK_LIMIT_C
from src.models.db import DatasheetDB
from src.physics.simulate import SimulationRun

Severity = Literal["CRITICAL", "WARNING", "PASS"]
MIN_NTC_NMC = 6    # Rule 3: high-density NMC packs need at least 6 NTCs to see the hotspot (team design rule)


class ConflictAlert(BaseModel):
    rule_id: str
    rule: Literal["thermal-electrical", "electro-mechanical", "protection-sensing"]
    title: str
    subsystems: list[str]
    requirements: list[str]
    severity: Severity
    safety: bool = False
    detail: str
    fixes: list[str] = []


def _alert(rule_id, rule, title, subsystems, requirements, violated: bool, critical: bool, detail, fixes,
           safety=False) -> ConflictAlert:
    sev: Severity = ("CRITICAL" if critical else "WARNING") if violated else "PASS"
    return ConflictAlert(rule_id=rule_id, rule=rule, title=title, subsystems=subsystems, requirements=requirements,
                         severity=sev, safety=safety and violated, detail=detail, fixes=fixes if violated else [])


def detect_conflicts(run: SimulationRun, db: DatasheetDB) -> list[ConflictAlert]:
    d, r = run.design, run.result
    cell, cooling, busbar = db.get_cell(d.cell_id), db.get_cooling(d.cooling_id), db.get_busbar(d.busbar_id)
    fuse, bms = db.get_protection(d.fuse_id), db.get_protection(d.bms_id)
    wh_per_kg = r.nominal_energy_kwh * 1000 / r.mass_kg
    te, em, ps = "thermal-electrical", "electro-mechanical", "protection-sensing"
    return [
        _alert("CF-TE-01", te, "Peak cell temperature over limit", ["thermal", "electrical", "cooling"],
               ["REQ-TH-01"], r.t_peak_c > T_PEAK_LIMIT_C, True,
               f"{r.t_peak_c:.1f} °C peak vs {T_PEAK_LIMIT_C:g} °C at {d.charge_c_rate:g} C after a ride "
               f"(plug-in at {r.t_charge_start_c:.1f} °C); {r.heat_gen_w:.0f} W generated vs "
               f"{r.heat_reject_w:.0f} W rejected on average",
               ["stronger cooling (lower R_th) or PCM buffer", "lower charge C-rate", "Cu busbars",
                "thermal-aware charging that waits for the pack to cool"], safety=True),
        _alert("CF-TE-02", te, "Charge heat exceeds steady cooling capacity", ["thermal", "cooling"],
               ["REQ-TH-01"], r.heat_gen_w > cooling.q_dissipation_w, False,
               f"{r.heat_gen_w:.0f} W generated vs {cooling.q_dissipation_w:.0f} W rejected at ΔT = 10 K "
               f"({cooling.name}); the charge relies on thermal mass"
               + (f" and {r.heat_pcm_w:.0f} W of PCM latent absorption" if r.heat_pcm_w > 0 else ""),
               ["size cooling for the charge heat", "add PCM / thermal mass", "reduce charge current"]),
        _alert("CF-TE-03", te, "BMS derating stretches the charge", ["thermal", "control"], ["REQ-CH-01"],
               r.charge_time_derated_min > r.charge_time_10_80_min + 1.0,
               r.requirement_status.get("REQ-CH-01") == "FAIL",
               f"{r.charge_time_10_80_min:.0f} min nominal → {r.charge_time_derated_min:.0f} min with derating",
               ["reduce heat so derating never starts", "pre-cool or start the charge cooler"]),
        _alert("CF-EM-01", em, "Mass over chassis envelope", ["electrical", "mechanical"], ["REQ-ME-01"],
               r.requirement_status["REQ-ME-01"] == "FAIL", True,
               f"{r.mass_kg:.1f} kg; {r.n_cells} × {cell.chemistry} cells at {wh_per_kg:.0f} Wh/kg pack level",
               ["higher specific-energy chemistry", "fewer cells in parallel", "lighter cooling/enclosure"]),
        _alert("CF-EM-02", em, "Volume over under-seat bay", ["electrical", "mechanical"], ["REQ-ME-02"],
               r.requirement_status["REQ-ME-02"] == "FAIL", True,
               f"{r.volume_l:.1f} L for {r.n_cells} cells of {cell.volume_l * 1000:.0f} cm³ "
               f"+ {cooling.volume_l:g} L cooling",
               ["higher energy-density cells", "fewer cells", "conduction cooling instead of ducts"]),
        _alert("CF-PS-01", ps, "Fuse trips at peak discharge", ["protection", "electrical"], [],
               r.peak_discharge_a > fuse.rating_a, True,
               f"2 C peak {r.peak_discharge_a:.0f} A vs {fuse.rating_a:g} A {fuse.name}",
               ["fuse rated ≥ 1.25 × peak (below busbar/BMS limits)", "limit controller peak current"]),
        _alert("CF-PS-02", ps, "BMS rating below peak discharge", ["protection", "electrical"], [],
               r.peak_discharge_a > bms.rating_a, True,
               f"2 C peak {r.peak_discharge_a:.0f} A vs {bms.rating_a:g} A {bms.name}",
               ["higher-current BMS", "limit controller peak current"]),
        _alert("CF-PS-03", ps, "Busbar strip over ampacity at peak", ["protection", "electrical", "thermal"],
               ["REQ-TH-01"], r.busbar_strip_current_a > busbar.ampacity_a, False,
               f"{r.busbar_strip_current_a:.1f} A per strip vs {busbar.ampacity_a:g} A ({busbar.name})",
               ["thicker/wider strip", "copper busbar"], safety=True),
        _alert("CF-PS-04", ps, "Too few NTCs for a high-density NMC pack", ["sensing", "thermal"], ["REQ-TH-01"],
               cell.chemistry == "NMC" and d.n_ntc < MIN_NTC_NMC, False,
               f"{d.n_ntc} NTCs on {r.n_cells} NMC cells (rule: ≥ {MIN_NTC_NMC}); the BMS may miss the hotspot",
               [f"≥ {MIN_NTC_NMC} NTCs incl. one at the thermal centre"]),
        _alert("CF-PS-05", ps, "More NTCs than BMS inputs", ["sensing", "protection"], [],
               d.n_ntc > (bms.ntc_channels or 0), True,
               f"{d.n_ntc} NTCs vs {bms.ntc_channels} inputs on {bms.name}", ["BMS with more NTC inputs"]),
        _alert("CF-PS-06", ps, "Charge rate above cell limit", ["electrical", "cell", "control"], ["REQ-CH-01"],
               d.charge_c_rate > cell.max_charge_c, True,
               f"{d.charge_c_rate:g} C vs {cell.max_charge_c:g} C max for {cell.name}",
               ["lower charge rate", "cell rated for faster charge"], safety=True),
    ]
