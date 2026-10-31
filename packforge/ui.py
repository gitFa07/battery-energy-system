"""HTML pieces for the Streamlit UI: verdict, requirement grid, KPI table.

The grid draws every requirement and interface rule as one cell of a pack seen from above (designs × checks). Only
failures carry colour: fail = solid orange, warning = orange ring, pass = faint. Colours resolve against
`currentColor`, so the same markup reads on the light and the dark theme.
"""

from __future__ import annotations

import re
from html import escape

from .checks import Finding
from .engine import DesignResult, Ranking, Recommendation
from .figures import design_color
from .metrics import KPIS, METRICS, fmt
from .schema import Requirement, Study

CSS = """
<style>
.pf { --alert:#C2410C; --accent:#2E75B6; --quiet:color-mix(in srgb, currentColor 20%, transparent);
      --muted:color-mix(in srgb, currentColor 70%, transparent); --line:color-mix(in srgb, currentColor 16%, transparent);
      font-variant-numeric: tabular-nums; }
.pf .vh { position:absolute; width:1px; height:1px; overflow:hidden; clip-path:inset(50%); white-space:nowrap; }
.pf-mast { margin:0 0 .9rem; font-size:.95rem; max-width:75ch; }
.pf-mast span { color:var(--muted); }
.pf-mast b { font-family:"Barlow Semi Condensed", Barlow, sans-serif; font-weight:600; font-size:1.05rem;
             margin-right:.6rem; }
.pf-verdict h1 { font-family:"Barlow Semi Condensed", Barlow, sans-serif; font-weight:600; font-size:2.6rem;
                 line-height:1.08; margin:0; padding:0; text-wrap:balance; }
.pf-verdict h1 span { display:block; font-size:1.35rem; line-height:1.3; font-weight:600; color:var(--muted); }
.pf-verdict.none h1 { color:var(--alert); }
.pf-verdict p { margin:.55rem 0 0; max-width:72ch; font-size:1.05rem; }
.pf-scroll { overflow-x:auto; margin:1.4rem 0 .4rem; }
.pf-grid { border-collapse:separate; border-spacing:0; }
.pf-grid caption { caption-side:bottom; text-align:left; color:var(--muted); font-size:.85rem; padding-top:.5rem; }
.pf-grid th, .pf-grid td { padding:3px; text-align:center; font-weight:500; border:0; background:none; }
.pf-grid thead th { font-size:.78rem; color:var(--muted); line-height:1.1; }
.pf-grid thead tr:first-child th { text-align:left; font-size:.85rem; color:inherit; font-weight:600;
                                   border-bottom:1px solid var(--line); padding-bottom:4px; }
.pf-grid .g0 { padding-left:14px; }
.pf-grid tbody th { text-align:left; padding:6px 18px 6px 10px; white-space:nowrap; font-weight:600; }
.pf-grid tbody th small { display:block; font-weight:400; color:var(--muted); font-size:.82rem; }
.pf-grid tr.rec th { box-shadow:inset 3px 0 0 var(--accent); }
.pf-grid .score { padding-left:18px; text-align:right; white-space:nowrap; font-size:1.05rem; }
.pf-grid .score small { display:block; color:var(--alert); font-size:.8rem; font-weight:600; }
.pf .sw { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:7px; vertical-align:1px; }
.pf .c { display:inline-block; width:18px; height:18px; border-radius:50%; vertical-align:middle; box-sizing:border-box;
         background:var(--quiet); }
.pf .c.warn { background:none; border:2.5px solid var(--alert); }
.pf .c.fail { background:var(--alert); }
.pf .c.sm { width:11px; height:11px; margin-right:6px; vertical-align:0; }
.pf .c.sm.warn { border-width:2px; }
.pf-legend { display:flex; flex-wrap:wrap; gap:.4rem 1.4rem; color:var(--muted); font-size:.85rem; margin:0 0 1.2rem; }
.pf-alt { display:grid; grid-template-columns:minmax(12rem, max-content) 1fr; gap:.45rem 1.2rem; margin:0 0 1rem;
          max-width:72rem; }
.pf dl.pf-alt, .pf-alt dt, .pf-alt dd { padding:0; margin-left:0; }
.pf-alt dt { font-weight:600; }
.pf .id { white-space:nowrap; }
.pf-alt dd { margin:0; }
.pf-alt dd > span { opacity:.7; }
.pf-kpi { border-collapse:collapse; width:100%; font-size:.95rem; }
.pf-kpi th, .pf-kpi td { border:0; border-bottom:1px solid var(--line); padding:7px 10px; text-align:right;
                          vertical-align:top; background:none; }
.pf-kpi thead th { font-weight:600; white-space:nowrap; }
.pf-kpi th:first-child, .pf-kpi td.ev { text-align:left; }
.pf-kpi tbody th { font-weight:500; }
.pf-kpi tbody th small, .pf-kpi td.ev { display:block; color:var(--muted); font-size:.82rem; font-weight:400; }
.pf-kpi td.ev { display:table-cell; }
.pf-kpi td { white-space:nowrap; }
.pf-kpi td.fail { color:var(--alert); font-weight:600; }
@media (max-width: 640px) {
  .pf-verdict h1 { font-size:1.9rem; }
  .pf-alt { grid-template-columns:1fr; gap:.15rem; }
  .pf-alt dd { margin-bottom:.5rem; }
}
</style>
"""


def _text(s: str) -> str:
    """Escape, and keep check ids like REQ-08 on one line."""
    return re.sub(r"\b(?:REQ|IF)-\d+", lambda m: f'<span class="id">{m.group(0)}</span>', escape(s))


def split_name(name: str) -> tuple[str, str]:
    """'Option B — LFP 16S8P, passive' → ('Option B', 'LFP 16S8P, passive')."""
    head, _, tail = name.partition(" — ")
    return head, tail


def masthead(study: Study, hot: bool, heat: float) -> str:
    run = (f"Simulating {study.ambient_c:g} °C ambient, charging "
           + ("right after the ride" if hot else "from ambient")
           + (f", cells making {heat:g}× the modelled heat" if heat != 1 else "") + ".")
    return f'<div class="pf"><p class="pf-mast"><b>PackForge</b><span>{escape(study.application)}. {escape(run)}</span></p></div>'


def verdict(recs: list[Recommendation], results: list[DesignResult]) -> str:
    if not recs:
        return ('<div class="pf pf-verdict none"><h1>No design meets every must requirement</h1>'
                '<p>Open <b>Conflicts</b> for the cause chain and candidate fixes, or add an option.</p></div>')
    by_id = {r.design.id: r for r in results}
    top = recs[0]
    head, tail = split_name(by_id[top.design_id].design.name)
    why = top.why[0].upper() + top.why[1:]
    return (f'<div class="pf pf-verdict"><h1>Recommended: {escape(head)}<span>{escape(tail)}</span></h1>'
            f'<p>{_text(why)}.</p></div>')


def alternatives(recs: list[Recommendation]) -> str:
    """The second and third answers of `recommend()`, as a definition list (headline: why)."""
    rows = []
    for rec in recs[1:]:
        label, _, name = rec.headline.partition(": ")
        rows.append(f"<dt>{escape(label)}</dt><dd>{escape(name)} <span>({_text(rec.why)})</span></dd>")
    return f'<div class="pf"><dl class="pf-alt">{"".join(rows)}</dl></div>' if rows else ""


def _cell(f: Finding, small: bool = False) -> str:
    word = {"pass": "pass", "warn": "warning", "fail": "fail"}[f.severity]
    tip = f"{f.id} {f.title}: {word}. {f.detail}"
    return (f'<span class="c {f.severity}{" sm" if small else ""}" title="{escape(tip)}">'
            f'<span class="vh">{escape(f.id)} {word}</span></span>')


def requirement_grid(results: list[DesignResult], ranking: list[Ranking], study: Study,
                     recommended: str | None) -> str:
    """Designs (ranked) × requirement and interface-rule checks. Colour swatch = the design's chart colour."""
    color = {r.design.id: design_color(i) for i, r in enumerate(results)}
    by_id = {r.design.id: r for r in results}
    groups = [("Must", [q.id for q in study.requirements if q.priority == "must"]),
              ("Should", [q.id for q in study.requirements if q.priority == "should"]),
              ("Interface rules", list(dict.fromkeys(f.id for r in results for f in r.findings
                                                     if f.requirement is None)))]
    groups = [(g, ids) for g, ids in groups if ids]
    text = {q.id: q.text for q in study.requirements}
    first = {ids[0] for _, ids in groups}

    top = '<th scope="col">Design</th>' + "".join(
        f'<th scope="colgroup" colspan="{len(ids)}" class="g0">{g}</th>' for g, ids in groups) + \
        '<th scope="col" class="score">Score</th>'
    sub = "<th></th>" + "".join(
        f'<th scope="col" class="{"g0" if i in first else ""}" title="{escape(i + " " + text.get(i, ""))}">'
        f'{escape(i.split("-")[-1])}</th>' for _, ids in groups for i in ids) + "<th></th>"

    body = []
    for rk in ranking:
        r = by_id[rk.design_id]
        f_by = {f.id: f for f in r.findings}
        head, tail = split_name(r.design.name)
        cells = "".join(f'<td class="{"g0" if i in first else ""}">{_cell(f_by[i]) if i in f_by else ""}</td>'
                        for _, ids in groups for i in ids)
        out = "" if rk.eligible else (f'<small title="{escape("; ".join(rk.reasons))}">disqualified</small>')
        body.append(f'<tr class="{"rec" if r.design.id == recommended else ""}"><th scope="row">'
                    f'<span class="sw" style="background:{color[r.design.id]}"></span>{escape(head)}'
                    f'<small>{escape(tail)}</small></th>{cells}<td class="score">{rk.score:.0f}{out}</td></tr>')

    legend = ('<div class="pf-legend"><span><span class="c sm fail"></span>fail (a failed must requirement or '
              'critical rule disqualifies)</span><span><span class="c sm warn"></span>warning</span>'
              '<span><span class="c sm"></span>pass</span></div>')
    return (f'<div class="pf"><div class="pf-scroll"><table class="pf-grid"><caption>Designs ranked by score. '
            f'Hover a cell for the check and its result.</caption><thead><tr>{top}</tr><tr>{sub}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>{legend}</div>')


def _limit(q: Requirement) -> str:
    n = lambda v: f"{v:,.0f}" if abs(v) >= 1000 else f"{v:g}"  # noqa: E731
    u = f" {q.unit}" if q.unit and q.unit != "₹" else ""
    cur = "₹" if q.unit == "₹" else ""
    if q.min is not None and q.max is not None:
        rng = f"{cur}{n(q.min)}–{n(q.max)}{u}"
    elif q.max is not None:
        rng = f"≤ {cur}{n(q.max)}{u}"
    else:
        rng = f"≥ {cur}{n(q.min)}{u}"
    return f"{q.id} {q.priority}: {rng}"


def kpi_table(results: list[DesignResult], study: Study) -> str:
    """KPI rows × designs; the requirement each KPI is checked against sits under its name."""
    req = {q.metric: q for q in study.requirements}
    head = "".join(f'<th scope="col" title="{escape(r.design.name)}"><span class="sw" '
                   f'style="background:{design_color(i)}"></span>{escape(split_name(r.design.name)[0])}</th>'
                   for i, r in enumerate(results))
    rows = []
    for k in KPIS:
        q = req.get(k)
        label = escape(METRICS[k].label) + (f"<small>{escape(_limit(q))}</small>" if q else "")
        cells = []
        for r in results:
            f = next((x for x in r.findings if q and x.requirement == q.id), None)
            mark = _cell(f, small=True) if f and f.severity != "pass" else ""
            cls = f' class="{f.severity}"' if f and f.severity == "fail" else ""
            cells.append(f"<td{cls}>{mark}{escape(fmt(k, r.metrics[k]))}</td>")
        rows.append(f'<tr><th scope="row">{label}</th><td class="ev">{escape(METRICS[k].evidence)}</td>'
                    f'{"".join(cells)}</tr>')
    return (f'<div class="pf"><div class="pf-scroll" style="margin-top:0"><table class="pf-kpi"><thead><tr>'
            f'<th scope="col">KPI</th><th scope="col" style="text-align:left">Evidence</th>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div></div>')
