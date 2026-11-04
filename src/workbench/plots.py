"""Plotly figures for the VoltTwin workbench and report.

Colours (validated with the dataviz palette checker on the light #FFFFFF and dark #0F1720 surfaces):
designs take DESIGN_COLORS in study order and keep them in every chart; ALERT marks limits and failures only;
MEASURED is the neutral ink for real data. Heat paths use two one-hue ramps — sources purple, sinks teal — so the
legend reads as "where heat comes from / where it goes" rather than five unrelated categories.
No dual axes: quantities with different units get stacked panels on a shared time axis.
"""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.config import BMS_CUTOFF_C, T_PEAK_LIMIT_C
from src.physics.pybamm_runner import CellElectrochem
from src.physics.replay import Replay
from src.pipeline import DesignEvaluation, StudyEvaluation

DESIGN_COLORS = ["#2E75B6", "#1B9E77", "#B38A18", "#8E6BBF"]
ALERT = "#D9531E"
MEASURED = "#8A929E"
SOURCES = {"Cells (I²R + entropic)": "#5B3F99", "Busbar I²R": "#A88BD6"}
SINKS = {"Rejected to ambient": "#0F6E6A", "PCM latent": "#2AA3A0", "Stored (temperature rise)": "#8FD3CF"}
GRID = "rgba(128,128,128,0.22)"
_BASE = dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(size=13),
             legend=dict(orientation="h", yanchor="top", y=-0.18, x=0), margin=dict(l=60, r=20, t=50, b=40))


def design_colors(study: StudyEvaluation) -> dict[str, str]:
    return {ev.id: DESIGN_COLORS[i % len(DESIGN_COLORS)] for i, ev in enumerate(study.designs)}


def _axes(fig: go.Figure) -> go.Figure:
    fig.update_xaxes(gridcolor=GRID, zeroline=False, showline=False)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, showline=False)
    return fig


def radar(study: StudyEvaluation) -> go.Figure:
    """Margin-to-limit (0–100): 50 = at the requirement limit, 100 = full headroom, inside 50 = violated."""
    colors = design_colors(study)
    axes = list(study.designs[0].ranked.margins)
    fig = go.Figure()
    theta = axes + axes[:1]
    fig.add_trace(go.Scatterpolar(r=[50] * len(theta), theta=theta, mode="lines", name="Requirement limit",
                                  line=dict(color=ALERT, width=1.5, dash="dash"), hoverinfo="skip"))
    for ev in study.designs:
        vals = [ev.ranked.margins[a] for a in axes]
        fig.add_trace(go.Scatterpolar(
            r=vals + vals[:1], theta=theta, mode="lines+markers", name=f"{ev.run.design.name} — {ev.ranked.verdict}",
            line=dict(color=colors[ev.id], width=2), marker=dict(size=8),
            hovertemplate="%{theta}: %{r:.0f} / 100<extra>" + ev.run.design.name + "</extra>"))
    fig.update_layout(**_BASE, title="Trade-off radar — margin to each requirement limit",
                      polar=dict(bgcolor="rgba(0,0,0,0)",
                                 radialaxis=dict(range=[0, 100], tickvals=[0, 25, 50, 75, 100], gridcolor=GRID,
                                                 angle=90, tickangle=90),
                                 angularaxis=dict(gridcolor=GRID)))
    return fig


def transient(ev: DesignEvaluation, color: str) -> go.Figure:
    """Hottest-cell temperature and pack voltage over ride + charge, with and without BMS derating."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.6, 0.4],
                        subplot_titles=("Hottest-cell temperature (°C)", "Pack voltage (V)"))
    runs = [(ev.run.nominal, "No derating (design capability)", "dash"), (ev.run.derated, "With BMS derating", "solid")]
    for tr, label, dash in runs:
        minutes = tr.t_s / 60
        fig.add_trace(go.Scatter(x=minutes, y=tr.t_core_c, name=label, legendgroup=label, mode="lines",
                                 line=dict(color=color, width=2, dash=dash),
                                 hovertemplate="%{y:.1f} °C<extra>" + label + "</extra>"), row=1, col=1)
        fig.add_trace(go.Scatter(x=minutes, y=tr.voltage_v, name=label, legendgroup=label, showlegend=False,
                                 mode="lines", line=dict(color=color, width=2, dash=dash),
                                 hovertemplate="%{y:.1f} V<extra>" + label + "</extra>"), row=2, col=1)
    plug = float(ev.run.nominal.t_s[ev.run.nominal.charge()][0]) / 60
    for y, text in ((T_PEAK_LIMIT_C, f"REQ-TH-01 limit {T_PEAK_LIMIT_C:g} °C"),
                    (BMS_CUTOFF_C, f"BMS cutoff {BMS_CUTOFF_C:g} °C")):
        fig.add_hline(y=y, line=dict(color=ALERT, width=1.2, dash="dot"), row=1, col=1,
                      annotation_text=text, annotation_position="top left", annotation_font_color=ALERT)
    fig.add_vline(x=plug, line=dict(color=MEASURED, width=1, dash="dot"))
    fig.add_annotation(x=plug, y=1.0, yref="paper", text="plug-in", showarrow=False, xanchor="left",
                       font=dict(color=MEASURED))
    fig.update_xaxes(title_text="time (min): ride, then fast charge 10 → 80 %", row=2, col=1)
    fig.update_layout(**_BASE, height=560, hovermode="x unified",
                      title=f"{ev.run.design.name}: electro-thermal fast-charge transient")
    return _axes(fig)


def heat_breakdown(study: StudyEvaluation) -> go.Figure:
    """Mean heat during the charge: sources (generated) vs sinks (rejected, PCM, stored) per design."""
    xs_design, xs_side = [], []
    for ev in study.designs:
        xs_design += [ev.run.design.name] * 2
        xs_side += ["Generated", "Removed / stored"]
    fig = go.Figure()

    def add(name: str, color: str, per_design: list[tuple[float, float]]):
        y = [v for pair in per_design for v in pair]
        fig.add_trace(go.Bar(x=[xs_design, xs_side], y=y, name=name, marker=dict(color=color, line=dict(width=0)),
                             hovertemplate="%{y:.1f} W<extra>" + name + "</extra>"))

    rs = [ev.run.result for ev in study.designs]
    add("Cells (I²R + entropic)", SOURCES["Cells (I²R + entropic)"],
        [(r.heat_cells_w + r.heat_reversible_w, 0) for r in rs])
    add("Busbar I²R", SOURCES["Busbar I²R"], [(r.heat_busbar_w, 0) for r in rs])
    add("Rejected to ambient", SINKS["Rejected to ambient"], [(0, r.heat_reject_w) for r in rs])
    add("PCM latent", SINKS["PCM latent"], [(0, r.heat_pcm_w) for r in rs])
    add("Stored (temperature rise)", SINKS["Stored (temperature rise)"],
        [(0, max(r.heat_gen_w - r.heat_reject_w - r.heat_pcm_w, 0)) for r in rs])
    fig.update_layout(**_BASE, barmode="stack", bargap=0.25, title="Heat generation vs cooling rejection "
                      "(mean over the fast charge)", yaxis_title="W")
    fig.update_layout(legend_traceorder="normal")
    return _axes(fig)


def validation_overlay(rp: Replay) -> go.Figure:
    """Measured proxy-cell log vs VoltTwin's datasheet cell model (not fitted)."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        subplot_titles=(f"Cell voltage (V) — RMSE {rp.v_rmse_op_mv:.0f} mV at SoC ≥ 10 %, "
                                        f"{rp.v_rmse_mv:.0f} mV full range",
                                        f"Surface temperature (°C) — rise {rp.t_rise_meas_k:.1f} K measured, "
                                        f"{rp.t_rise_pred_k:.1f} K predicted"))
    m = rp.t_s / 60
    fig.add_trace(go.Scatter(x=m, y=rp.v_meas, name="Measured (LG M50LT proxy)", legendgroup="meas",
                             line=dict(color=MEASURED, width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=m, y=rp.v_pred, name="VoltTwin model (datasheet values)", legendgroup="model",
                             line=dict(color=DESIGN_COLORS[0], width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=m, y=rp.t_meas, name="Measured (LG M50LT proxy)", legendgroup="meas", showlegend=False,
                             line=dict(color=MEASURED, width=2)), row=2, col=1)
    fig.add_trace(go.Scatter(x=m, y=rp.t_pred, name="VoltTwin model (datasheet values)", legendgroup="model",
                             showlegend=False, line=dict(color=DESIGN_COLORS[0], width=2)), row=2, col=1)
    fig.update_xaxes(title_text="time (min)", row=2, col=1)
    fig.update_layout(**_BASE, height=560, hovermode="x unified", title=f"Validation overlay: {rp.label}")
    return _axes(fig)


def cell_curves(curves: dict[str, CellElectrochem], colors: dict[str, str]) -> go.Figure:
    """Per-cell charge voltage and heat vs SoC from PyBaMM SPMe (or the surrogate)."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                        subplot_titles=("Cell terminal voltage during charge (V)", "Cell heat (W)"))
    for label, ec in curves.items():
        name = f"{label} — {ec.engine} ({ec.parameter_set})"
        c = colors.get(label, MEASURED)
        fig.add_trace(go.Scatter(x=np.asarray(ec.soc) * 100, y=ec.voltage_v, name=name, legendgroup=name,
                                 line=dict(color=c, width=2)), row=1, col=1)
        fig.add_trace(go.Scatter(x=np.asarray(ec.soc) * 100, y=ec.heat_w, name=name, legendgroup=name,
                                 showlegend=False, line=dict(color=c, width=2)), row=2, col=1)
    fig.update_xaxes(title_text="SoC (%)", row=2, col=1)
    fig.update_layout(**_BASE, height=520, hovermode="x unified", title="Cell electrochemistry (10 → 80 % charge)")
    return _axes(fig)
