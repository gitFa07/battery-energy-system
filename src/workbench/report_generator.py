"""Design & safety traceability report (Markdown + self-contained HTML) and the scaled 1S-4P bench protocol.

Bench protocol: 1 series × 4 parallel cells of the selected design's cell, driven at the same *per-cell* currents
as the pack (ride, then fast charge), in still lab air. Expected ΔT comes from the same lumped thermal model with a
bench cooling path R_th = 1 / (h · A_block). The bench cannot reproduce the pack's thermal environment; its purpose
is to measure per-cell heat: measured ΔT / predicted ΔT is the cell-heat factor to feed back into the robustness
check (real-log replays already suggest 2-4x).
"""

from __future__ import annotations

import html
import math
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from src.config import BMS_CUTOFF_C
from src.models.db import DatasheetDB
from src.models.schemas import CoolingSpec, ModuleDesignInput
from src.physics.electrical import pack_electrical
from src.physics.replay import real_logs, replay_log
from src.physics.thermal import RIDE_C, simulate_cycle
from src.pipeline import DesignEvaluation, StudyEvaluation
from src.workbench import plots, views

BENCH_S, BENCH_P = 1, 4
BENCH_AMBIENT_C = 25.0         # lab ambient — no heated chamber on the bench (safety)
BENCH_H_W_M2K = 8.0            # still air around a bare 2×2 block (assumption, typical 5-10)
BENCH_FUSE_FACTOR = 1.5        # inline fuse rating ≥ 1.5 × largest bench current
BENCH_PURPOSE = ("Four cells of the selected design's cell in parallel (1S), driven at the pack's per-cell currents "
                 "(ride, then fast charge) in still lab air. The bench cannot reproduce the pack's thermal "
                 "environment; it measures per-cell heat: measured ΔT / expected ΔT is the cell-heat factor for the "
                 "robustness check.")

LIMITATIONS = [
    "Cell resistance carries a 15 % beginning-of-life margin for ageing and spread (A-EL-01); it is held at its "
    "25 °C value, which over-estimates heat at 40-55 °C — but real-log replays show the model still under-predicts "
    "the temperature rise 2-4x, so the net bias is optimistic.",
    "Uniform contact and interconnect resistance: every busbar link is identical; weld variation and current "
    "imbalance between parallel cells are not modelled.",
    "One lumped thermal node (1D, 0D in space) instead of a 3D/CFD model: no cell-to-cell gradient beyond the "
    "core-to-can rise of the hottest cell; enclosure air, duct flow and fin geometry are reduced to one R_th.",
    "PyBaMM uses reference cells (Marquis2019 NMC, Prada2013 LFP) scaled by capacity — a physics cross-check, "
    "not a model of these cells.",
    "Cell values are generic 21700 class values, not a named part. Only NMC has measured (proxy) data; the LFP cell "
    "is not validated.",
    "Round-1 numbers are submission targets, not measurements; where they disagree beyond tolerance the reason is "
    "listed.",
    "No design is claimed compliant with AIS-156 or any other standard.",
]


@dataclass
class BenchProtocol:
    cell_name: str
    n_cells: int
    v_nom_v: float
    capacity_ah: float
    ride_current_a: float
    charge_current_a: float
    load_resistor_ohm: float
    load_resistor_power_w: float
    fuse_a: float
    cv_limit_v: float
    uv_cutoff_v: float
    ot_cutoff_c: float
    ambient_c: float
    r_th_k_w: float
    expected_ride_dt_k: float
    expected_peak_dt_k: float
    expected_charge_min: float
    ntc_positions: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    safety: list[str] = field(default_factory=list)


def bench_protocol(design: ModuleDesignInput, db: DatasheetDB) -> BenchProtocol:
    cell, busbar = db.get_cell(design.cell_id), db.get_busbar(design.busbar_id)
    bench = design.model_copy(update={"id": f"{design.id}_bench", "n_series": BENCH_S, "n_parallel": BENCH_P,
                                      "ambient_c": BENCH_AMBIENT_C})
    d_m, h_m = cell.diameter_mm / 1000, cell.height_mm / 1000
    side = 2 * d_m                                           # 2×2 block footprint
    area = 4 * side * h_m + 2 * side**2
    r_th = 1 / (BENCH_H_W_M2K * area)
    still_air = CoolingSpec(id="bench_still_air", name="Bench: bare 2×2 block in still air", kind="passive",
                            r_th_k_w=r_th, q_dissipation_w=10 / r_th, fan_power_w=0, pcm_mass_kg=0,
                            pcm_latent_j_kg=0, pcm_melt_c=None, mass_kg=0, volume_l=0, cost_usd=0,
                            source=f"h = {BENCH_H_W_M2K:g} W/m²K over {area * 1e4:.0f} cm² exposed block surface")
    pe = pack_electrical(bench, cell, busbar)
    tr = simulate_cycle(bench, cell, still_air, pe, derate=False)
    ride = tr.phase == "ride"
    i_ride = RIDE_C * cell.capacity_ah * BENCH_P
    i_chg = design.charge_c_rate * cell.capacity_ah * BENCH_P
    r_load = cell.v_nom_v / i_ride
    return BenchProtocol(
        cell_name=cell.name, n_cells=BENCH_S * BENCH_P, v_nom_v=pe.v_nom_v, capacity_ah=pe.capacity_ah,
        ride_current_a=i_ride, charge_current_a=i_chg, load_resistor_ohm=r_load,
        load_resistor_power_w=2 * cell.v_max_v**2 / r_load,          # 2× margin at full-charge voltage
        fuse_a=math.ceil(BENCH_FUSE_FACTOR * max(i_ride, i_chg) / 5) * 5,
        cv_limit_v=cell.v_max_v, uv_cutoff_v=cell.v_min_v, ot_cutoff_c=BMS_CUTOFF_C, ambient_c=BENCH_AMBIENT_C,
        r_th_k_w=r_th,
        expected_ride_dt_k=float(tr.t_pack_c[ride].max() - BENCH_AMBIENT_C),
        expected_peak_dt_k=float(tr.t_core_c.max() - BENCH_AMBIENT_C),
        expected_charge_min=tr.charge_time_min,
        ntc_positions=[
            *(f"T{k}: mid-can of cell {k} (Kapton tape + thermal paste)" for k in range(1, 5)),
            "T5: thermal centre — in the gap between the 4 cells (expected hottest point)",
            "T6: positive busbar / nickel strip at the terminal weld",
            "T7: negative busbar / nickel strip at the terminal weld",
            "T8: ambient reference, 10 cm from the block, shielded from airflow",
        ],
        steps=[
            f"Condition: rest the block ≥ 2 h at {BENCH_AMBIENT_C:g} °C lab ambient; charge to 90 % SoC "
            f"(CC {i_chg / 2:.1f} A, CV {cell.v_max_v:g} V) and rest again until T1-T8 agree within 0.5 K.",
            f"Ride: discharge at {i_ride:.1f} A ({RIDE_C:g} C per cell) — electronic load in CC mode, or a "
            f"{r_load:.2f} Ω resistor (≥ {2 * cell.v_max_v**2 / r_load:.0f} W) — down to 10 % SoC by coulomb count "
            f"or {cell.v_min_v + 0.5:g} V, whichever first.",
            f"Plug in immediately: CC {i_chg:.1f} A ({design.charge_c_rate:g} C per cell) to 80 % SoC; CV at "
            f"{cell.v_max_v:g} V only if reached.",
            "Log V, I, T1-T8 at 1 Hz throughout; continue logging 30 min after the charge.",
            "Analyse: compare measured peak ΔT (T5 − T8) with the expected value below; the ratio is the cell-heat "
            "factor for the robustness check. Replay the log through the model (CSV: time_s, current_a, "
            "voltage_v, temp_c, soc, ambient_c) for voltage RMSE.",
        ],
        safety=[
            "Low voltage only: 1S (≤ 4.2 V) — no series string on the bench.",
            "Protected cells or a BMS/protection board on the block; hard firmware cutoffs: "
            f"V ≤ {cell.v_max_v:g} V, V ≥ {cell.v_min_v:g} V, T ≥ {BMS_CUTOFF_C:g} °C on any NTC → current off.",
            f"Inline fuse {math.ceil(BENCH_FUSE_FACTOR * max(i_ride, i_chg) / 5) * 5} A in the positive lead, "
            "rated for DC at the bench voltage.",
            "Block inside a fireproof LiPo bag / steel tray on a non-flammable surface; CO2 or Class D extinguisher "
            "and sand bucket within reach.",
            "Never unattended; stop on swelling, venting smell, hiss, or any NTC rising > 1 K/min.",
            "Cells inspected before the test (no dents, wrap damage); welds or holders, never soldered to the can.",
        ],
    )


def _md_table(df: pd.DataFrame) -> str:
    cols = [str(c) for c in df.columns]
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in df.itertuples(index=False):
        out.append("| " + " | ".join("" if v is None or (isinstance(v, float) and math.isnan(v)) else
                                     str(v).replace("|", "/") for v in row) + " |")
    return "\n".join(out)


def _bom_tables(ev: DesignEvaluation) -> tuple[pd.DataFrame, pd.DataFrame]:
    m = ev.run.mechanical
    mass = pd.DataFrame([{"Item": k, "Mass (kg)": round(v, 3)} for k, v in m.mass_breakdown_kg.items()]
                        + [{"Item": "TOTAL", "Mass (kg)": round(m.mass_kg, 2)}])
    cost = pd.DataFrame([{"Item": k, "Cost ($)": round(v, 2)} for k, v in m.cost_breakdown_usd.items()]
                        + [{"Item": "TOTAL", "Cost ($)": round(m.bom_cost_usd, 2)}])
    return mass, cost


def bench_table(b: BenchProtocol) -> pd.DataFrame:
    rows = [("Configuration", f"1S-{b.n_cells}P {b.cell_name}"), ("Nominal voltage", f"{b.v_nom_v:.2f} V"),
            ("Capacity", f"{b.capacity_ah:.1f} Ah"), ("Ride current", f"{b.ride_current_a:.1f} A"),
            ("Fast-charge current", f"{b.charge_current_a:.1f} A"),
            ("Load resistor (alternative to e-load)", f"{b.load_resistor_ohm:.2f} Ω, ≥ {b.load_resistor_power_w:.0f} W"),
            ("Inline fuse", f"{b.fuse_a:g} A"), ("Cutoffs", f"{b.uv_cutoff_v:g}–{b.cv_limit_v:g} V, {b.ot_cutoff_c:g} °C"),
            ("Lab ambient", f"{b.ambient_c:g} °C"), ("Bench R_th (model)", f"{b.r_th_k_w:.1f} K/W"),
            ("Expected ΔT after ride", f"{b.expected_ride_dt_k:.1f} K"),
            ("Expected peak ΔT (hottest cell)", f"{b.expected_peak_dt_k:.1f} K"),
            ("Expected charge 10–80 %", f"{b.expected_charge_min:.0f} min")]
    return pd.DataFrame(rows, columns=["Parameter", "Value"])


@dataclass
class Report:
    markdown: str
    html: str


def build_report(study: StudyEvaluation, db: DatasheetDB, rob: dict[float, dict[str, str]] | None = None,
                 selected: str | None = None) -> Report:
    ev = study.by_id(selected) if selected else (study.recommended or study.by_id(study.ranking[0].design_id))
    names = {e.id: e.run.design.name for e in study.designs}
    bench = bench_protocol(ev.run.design, db)
    nmc = next(c for c in db.list_cells() if c.chemistry == "NMC")
    replays = [replay_log(p, nmc) for p in real_logs()]
    mass, cost = _bom_tables(ev)
    design_df = pd.DataFrame([{"Field": k, "Value": v} for k, v in ev.run.design.model_dump().items()])
    gaps = views.target_gaps(study)
    gaps = gaps[gaps["Within"] == "NO"] if not gaps.empty else gaps
    conflicts = {e.id: views.conflicts_table(e) for e in study.designs}
    rec_line = (f"**Recommended: {study.recommended.run.design.name}** (TOPSIS closeness "
                f"{study.recommended.ranked.closeness:.2f})" if study.recommended
                else "**No design meets every requirement without a critical conflict.**")
    rob_note = ""
    if rob:
        flips = [names[k] for k, v in rob.get(1.5, {}).items() if v != rob[1.0].get(k)]
        rob_note = ("Real-log replays show the datasheet cell model under-predicts the temperature rise 2-4x. "
                    + (f"At 1.5x cell heat the verdict changes for: {', '.join(flips)}. "
                       "Treat the recommendation as provisional until the 1S-4P bench test measures the heat factor."
                       if flips else "Verdicts are unchanged at 1.5x cell heat."))

    sections: list[tuple[str, list]] = [
        ("Recommendation", [rec_line, views.ranking_table(study)]
         + ([rob_note, views.robustness_table(rob, names)] if rob else [])),
        (f"Selected architecture: {ev.run.design.name}", [design_df, "Mass breakdown", mass, "BOM cost breakdown", cost]),
        ("Requirements compliance matrix", [views.requirement_grid(study)]),
        ("Interface conflicts", [x for e in study.designs for x in
                                 (f"{e.run.design.name} — {e.ranked.verdict}",
                                  conflicts[e.id] if not conflicts[e.id].empty else "No conflicts.")]),
        ("Simulated vs Round-1 targets", [views.comparison_matrix(study),
                                          "Disagreements beyond tolerance (±10 % / ±3 K):",
                                          gaps if not gaps.empty else "None."]),
        ("Model assumptions and limitations", ["\n".join(f"- {x}" for x in LIMITATIONS), views.assumptions_table()]),
        ("Validation against measured data",
         ["TU Berlin LG M50LT internal-temperature dataset, DOI 10.14279/depositonce-25110 (CC BY 4.0) — a proxy "
          "for the generic NMC class cell; VoltTwin's cell is not fitted to it. The LFP cell is not validated.",
          views.replay_table(replays)]),
        (f"Traceability: {ev.run.design.name}", [views.traceability_table(ev)]),
        (f"Scaled 1S-{bench.n_cells}P low-voltage bench test protocol",
         [BENCH_PURPOSE, bench_table(bench), "NTC placement (8 points)", "\n".join(f"- {p}" for p in bench.ntc_positions),
          "Procedure", "\n".join(f"{i + 1}. {s}" for i, s in enumerate(bench.steps)),
          "Safety precautions", "\n".join(f"- {s}" for s in bench.safety)]),
    ]
    title = "VoltTwin Studio — Battery System Design & Safety Traceability Report"
    meta = (f"Generated {date.today().isoformat()} · engine: {ev.run.result.engine} · "
            f"cell heat factor × {study.heat_factor:g} · 48 V e-scooter pack, 40 °C ambient, ride then fast charge")

    md = [f"# {title}", "", meta, ""]
    for head, items in sections:
        md += [f"## {head}", ""]
        for it in items:
            md += [_md_table(it) if isinstance(it, pd.DataFrame) else str(it), ""]

    figs = [plots.radar(study), plots.transient(ev, plots.design_colors(study)[ev.id]), plots.heat_breakdown(study)]
    fig_html = "".join(f.to_html(full_html=False, include_plotlyjs=(i == 0), config={"displaylogo": False})
                       for i, f in enumerate(figs))
    body = [f"<h1>{html.escape(title)}</h1>", f"<p class='meta'>{html.escape(meta)}</p>"]
    for i, (head, items) in enumerate(sections):
        body.append(f"<h2>{html.escape(head)}</h2>")
        for it in items:
            if isinstance(it, pd.DataFrame):
                body.append(it.to_html(index=False, escape=True, na_rep="", border=0))
            else:
                text = str(it)
                if text.startswith("- ") or re.match(r"\d+\. ", text):
                    tag = "ul" if text.startswith("- ") else "ol"
                    lis = "".join(f"<li>{html.escape(line.split(' ', 1)[1])}</li>" for line in text.splitlines())
                    body.append(f"<{tag}>{lis}</{tag}>")
                else:
                    body.append(f"<p>{html.escape(text).replace('**', '')}</p>")
        if i == 0:
            body.append(f"<div class='figs'>{fig_html}</div>")
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>VoltTwin report</title><style>
body{{font-family:Barlow,Segoe UI,Arial,sans-serif;color:#1B2733;background:#fff;max-width:1150px;margin:2rem auto;padding:0 16px;line-height:1.45}}
h1{{color:#1F4E79;font-size:1.7rem}} h2{{color:#1F4E79;border-bottom:1px solid #D0D5DB;padding-bottom:.2rem;margin-top:2rem}}
.meta{{color:#5A6672}} table{{border-collapse:collapse;width:100%;font-size:.86rem;margin:.6rem 0 1rem}}
th,td{{border-bottom:1px solid #E3E7EC;padding:.3rem .45rem;text-align:left;vertical-align:top}} th{{background:#EDF1F5}}
.figs{{overflow-x:auto}}
</style></head><body>{''.join(body)}</body></html>"""
    return Report("\n".join(md), page)


def write_report(path: Path, report: Report) -> Path:
    path = Path(path)
    path.write_text(report.markdown if path.suffix == ".md" else report.html, encoding="utf-8")
    return path
