"""Self-contained HTML design report: requirements → options → results → conflicts → recommendation → traceability."""

from __future__ import annotations

from datetime import date
from html import escape

from . import figures
from .fit import load_calibration
from .engine import DesignResult, rank, recommend, traceability
from .metrics import KPIS, METRICS, fmt
from .schema import Study

ICON = {"pass": "✅", "warn": "⚠️", "fail": "❌", "": ""}

CSS = """
:root{--bg:#fff;--fg:#1d2330;--mut:#5b6475;--line:#e3e6ec;--ok:#1a7f37;--warn:#9a6700;--bad:#cf222e;--acc:#0b6bcb}
@media (prefers-color-scheme:dark){:root{--bg:#12151b;--fg:#e6e9ef;--mut:#9aa3b2;--line:#2b313c;--acc:#6cb6ff}}
body{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;max-width:1100px;margin:0 auto;padding:24px 16px}
h1{margin-bottom:0}h2{border-bottom:1px solid var(--line);padding-bottom:4px;margin-top:2em}
.mut{color:var(--mut)}table{border-collapse:collapse;width:100%;margin:8px 0;font-size:14px}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
th{color:var(--mut);font-weight:600}.wrap{overflow-x:auto}
.rec{border-left:4px solid var(--ok);padding:8px 12px;background:color-mix(in srgb,var(--ok) 8%,transparent)}
.fail{color:var(--bad)}.warn{color:var(--warn)}
.plotly-graph-div{background:#fff;border-radius:4px;margin:12px 0}
"""


def _table(head: list[str], rows: list[list[str]]) -> str:
    h = "".join(f"<th>{escape(x)}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="wrap"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def build_report(results: list[DesignResult], study: Study, stress: list[DesignResult] | None = None) -> str:
    """`stress`: the same designs re-run with extra unmodelled heat (`with_heat_factor`) — robustness section."""
    ranking = rank(results, study)
    by_id = {r.design.id: r for r in results}
    recs = recommend(results, study)
    parts = [f"<h1>Battery design report</h1><p class='mut'>{escape(study.application)} · ambient "
             f"{study.ambient_c:g} °C · generated {date.today():%d %b %Y} by PackForge</p>"]

    if recs:
        b = by_id[recs[0].design_id]
        risks = "".join(f"<li>{escape(f.id)} {escape(f.title)}: {escape(f.detail)}</li>" for f in b.warns) or "<li>none</li>"
        alts = "".join(f"<p><b>{escape(r.headline)}</b> — {escape(r.why)}</p>" for r in recs[1:])
        parts.append(f"<div class='rec'><b>{escape(recs[0].headline)}</b> — {escape(recs[0].why)}"
                     f"<br>Open risks:<ul>{risks}</ul>{alts}</div>")
    else:
        parts.append("<div class='rec fail'><b>No design meets every must-requirement and interface rule.</b></div>")

    parts.append("<h2>Requirements</h2>" + _table(
        ["ID", "Requirement", "Metric", "Limit", "Priority"],
        [[q.id, escape(q.text), escape(METRICS[q.metric].label),
          " ".join(x for x in (f"≥ {q.min:g}" if q.min is not None else "", f"≤ {q.max:g}" if q.max is not None else "")
                   if x) + f" {escape(q.unit)}", q.priority] for q in study.requirements]))

    parts.append("<h2>Design options</h2>" + _table(
        ["Design", "Description", "Cell", "Topology", "Cooling", "Sensing", "Charge control"],
        [[escape(r.design.name), escape(r.design.description), escape(r.design.cell.name),
          f"{r.design.topology.series}S{r.design.topology.parallel}P", escape(r.design.cooling.type),
          f"{r.design.sensing.n_temp_sensors} NTC ({escape(str(r.design.sensing.placement))})",
          f"{r.design.control.charge_c_rate:g}C, derate {r.design.control.derate_start_c:g}–"
          f"{r.design.control.derate_end_c:g} °C on {r.design.control.derate_on}"] for r in results]))

    if stress:
        factor = stress[0].design.cell.heat_factor
        alt = recommend(stress, study)
        same = bool(alt) and bool(recs) and alt[0].design_id == recs[0].design_id
        parts.append(f"<h2>Robustness to unmodelled heat (× {factor:g})</h2><p class='mut'>The hold-out check "
                     "under-predicts the measured temperature rise (see Validation), so every design is re-run with "
                     f"its cells generating {factor:g}× the modelled heat; the BMS observer is not told.</p>"
                     + _table(["Design", "Eligible (as modelled)", f"Eligible (heat × {factor:g})",
                               "Charge time (as modelled)", f"Charge time (heat × {factor:g})", "New fails"],
                              [[escape(a.design.name), "yes" if not a.fails else "no", "yes" if not b.fails else "no",
                                fmt("charge_time_min", a.metrics["charge_time_min"]),
                                fmt("charge_time_min", b.metrics["charge_time_min"]),
                                escape(", ".join(f.id for f in b.fails if f.id not in {x.id for x in a.fails}))]
                               for a, b in zip(results, stress)])
                     + (f"<p><b>Recommendation {'holds' if same else 'changes'}:</b> "
                        + (escape(alt[0].headline) if alt else "no design is eligible") + "</p>"))

    status = {r.design.id: {f.requirement: f.severity for f in r.findings if f.requirement} for r in results}
    req_by_metric = {q.metric: q.id for q in study.requirements}
    parts.append("<h2>Results</h2>" + _table(
        ["KPI", "Evidence"] + [escape(r.design.name) for r in results],
        [[escape(METRICS[k].label), METRICS[k].evidence] +
         [f"{ICON[status[r.design.id].get(req_by_metric.get(k), '')]} {fmt(k, r.metrics[k])}" for r in results]
         for k in KPIS]))
    parts.append(_table(["Rank", "Design", "Score", "Eligible"],
                        [[str(i), escape(by_id[rk.design_id].design.name), f"{rk.score:.0f}",
                          "yes" if rk.eligible else "no — " + escape("; ".join(rk.reasons))]
                         for i, rk in enumerate(ranking, 1)]))

    figs = [figures.radar(results, study), figures.timeseries(results, "charge", "Max cell temp °C"),
            figures.timeseries(results, "charge", "Pack current A")] + [figures.heatmap(r) for r in results]
    parts.append("<h2>Charts</h2>" + "".join(
        f.to_html(full_html=False, include_plotlyjs=(i == 0)) for i, f in enumerate(figs)))

    parts.append("<h2>Conflicts and fixes</h2>")
    for r in results:
        issues = r.fails + r.warns
        items = "".join(
            f"<li class='{f.severity}'><b>{ICON[f.severity]} {escape(f.id)} {escape(f.title)}</b> "
            f"<span class='mut'>[{escape(', '.join(f.subsystems))}]</span><br>{escape(f.detail)}"
            + (f"<br><i>Fixes:</i> {escape('; '.join(f.fixes))}" if f.fixes else "") + "</li>" for f in issues)
        parts.append(f"<h3>{escape(r.design.name)}</h3><ul>{items or '<li>No conflicts.</li>'}</ul>")

    parts.append("<h2>Traceability</h2><p class='mut'>Evidence ladder: datasheet → assumption → calculated → "
                 "estimated → simulated → measured</p>")
    for r in results:
        rows = traceability(r, study)
        parts.append(f"<h3>{escape(r.design.name)}</h3>" + _table(
            ["Req", "Result", "Status", "Evidence", "Model", "Assumptions"],
            [[x["requirement"], escape(x["result"]), ICON[x["status"]], x["evidence"], escape(x["model"]),
              escape(x["assumptions"])] for x in rows]))

    parts.append("<h2>Validation</h2>")
    for cell in {r.design.cell.id: r.design.cell for r in results}.values():
        cal = load_calibration(cell.id)
        if cal is None:
            parts.append(f"<p class='warn'>⚠️ <b>{escape(cell.name)}</b>: not validated against measured data — "
                         "class values only. Results for designs using it are model estimates.</p>")
            continue
        parts.append(f"<p><b>{escape(cell.name)}</b>: fitted on {len(cal['fit_logs'])} logs at 25–35 °C from the "
                     f"{escape(cal['proxy'])}; hold-out at {cal['holdout_temp_c']:g} °C on logs and a temperature "
                     "the fit never saw. The core runs up to "
                     f"{max(s['core_minus_surface_max_k'] for s in cal['holdout_summary'].values()):.1f} K above the "
                     "measured surface; the model has one node per cell.</p>" + _table(
            ["Hold-out set", "Logs", f"V RMSE, SOC ≥ {cal['op_soc_min']:.0%} (median / max)",
             "V RMSE, full range (median / max)", "T RMSE (median / max)", "Mean T rise measured / model"],
            [[kind, str(sm["n"]), f"{sm['v_rmse_op_mv_median']:.0f} / {sm['v_rmse_op_mv_max']:.0f} mV",
              f"{sm['v_rmse_mv_median']:.0f} / {sm['v_rmse_mv_max']:.0f} mV",
              f"{sm['t_rmse_k_median']:.2f} / {sm['t_rmse_k_max']:.2f} K",
              f"{sm['t_rise_meas_k_mean']:.1f} / {sm['t_rise_pred_k_mean']:.1f} K"]
             for kind, sm in cal["holdout_summary"].items()]))

    assumptions = {a.id: a for r in results for a in r.design.all_assumptions()}
    parts.append("<h2>Assumptions</h2>" + _table(
        ["ID", "Assumption", "Source", "Affects"],
        [[a.id, escape(a.text), escape(a.source), ", ".join(a.affects)] for a in assumptions.values()]))
    sources = sorted({s for r in results for s in r.design.cell.sources})
    parts.append("<h2>Data sources</h2><ul>" + "".join(f"<li>{escape(s)}</li>" for s in sources) + "</ul>")

    body = "\n".join(parts)
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><title>Battery design report</title><style>{CSS}</style>"
            f"</head><body>{body}</body></html>")
