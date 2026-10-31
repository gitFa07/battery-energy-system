"""Plotly figures shared by the UI and the HTML report.

Designs keep one colour across every chart (by position in the comparison). Backgrounds stay transparent so the
host page's theme shows through; the report puts charts on a light panel.
"""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from .engine import DesignResult
from .metrics import METRICS
from .schema import Study
from .sim import sensor_positions

SIGNALS = {"Max cell temp °C": "t_max", "BMS hotspot view °C": "t_bms_hot", "Hottest NTC °C": "t_sensed_max",
           "Pack current A": "current_a", "Pack voltage V": "v_pack", "Mean SOC": "soc_mean",
           "Mean cell heat W": "heat_w_mean"}

# Categorical, distinguishable in light and dark; orange is kept for alerts (fail / hot), not for designs.
DESIGN_COLORS = ["#2E75B6", "#1B9E77", "#C9A227", "#8E6BBF", "#D46A9F", "#6B7280"]
MEASURED_COLOR = "#8A929E"
GRID = "rgba(128,128,128,0.25)"
_BASE = {"paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)", "font": {"size": 13},
         "legend": {"orientation": "h", "yanchor": "top", "y": -0.3, "x": 0}, "hovermode": "x unified"}


def design_color(i: int) -> str:
    return DESIGN_COLORS[i % len(DESIGN_COLORS)]


def _rgba(hex_color: str, alpha: float) -> str:
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


def _split(name: str) -> tuple[str, str]:
    """'Option A — NMC + Al plate' → ('Option A', 'NMC + Al plate'); keeps long names out of chart titles."""
    head, _, tail = name.partition(" — ")
    return head, tail


def _axes(fig: go.Figure) -> go.Figure:
    fig.update_xaxes(gridcolor=GRID, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


def radar(results: list[DesignResult], study: Study) -> go.Figure:
    weights = study.score_weights
    labels = [METRICS[m].label for m in weights]
    fig = go.Figure()
    for i, r in enumerate(results):
        vals = []
        for m, w in weights.items():
            col = [x.metrics[m] for x in results]
            lo, hi = np.nanmin(col), np.nanmax(col)
            v = 0.5 if hi == lo else (r.metrics[m] - lo) / (hi - lo)
            vals.append(v if w > 0 else 1 - v)
        c = design_color(i)
        fig.add_trace(go.Scatterpolar(r=vals + vals[:1], theta=labels + labels[:1], fill="toself", name=r.design.name,
                                      line={"color": c, "width": 2}, fillcolor=_rgba(c, 0.15)))
    fig.update_layout(**{**_BASE, "hovermode": "closest", "legend": {**_BASE["legend"], "y": -0.08}},
                      title="Relative trade-off (outer = better)", height=520,
                      polar={"bgcolor": "rgba(0,0,0,0)",
                             "radialaxis": {"range": [0, 1], "showticklabels": False, "gridcolor": GRID},
                             "angularaxis": {"gridcolor": GRID}})
    return fig


def timeseries(results: list[DesignResult], scenario: str, label: str) -> go.Figure:
    fig = go.Figure()
    for i, r in enumerate(results):
        tr = getattr(r, scenario)
        fig.add_trace(go.Scatter(x=tr.t_s / 60, y=getattr(tr, SIGNALS[label])[:, 0], name=r.design.name, mode="lines",
                                 line={"color": design_color(i), "width": 2}))
    fig.update_layout(**_BASE, title=f"{label} — {scenario}", xaxis_title="time [min]", height=380,
                      margin={"t": 48})
    return _axes(fig)


def heatmap(r: DesignResult, zrange: tuple[float, float] | None = None) -> go.Figure:
    """`zrange`: shared colour scale so designs compare like for like (pass the min/max over all designs)."""
    tr = r.charge if r.metrics["t_max_charge_c"] >= r.metrics["t_max_drive_c"] else r.drive
    rows, cols = sensor_positions(r.design)
    lo, hi = zrange or (None, None)
    head, tail = _split(r.design.name)
    fig = go.Figure(go.Heatmap(z=tr.t_field_peak[0], colorscale="Inferno", zmin=lo, zmax=hi,
                               colorbar={"title": "°C", "thickness": 12},
                               hovertemplate="parallel group %{y}, cell %{x}<br>%{z:.1f} °C<extra></extra>"))
    fig.add_trace(go.Scatter(x=cols, y=rows, mode="markers", showlegend=False, hoverinfo="skip",
                             marker={"size": 12, "symbol": "circle-open", "color": "#4FD1C5", "line": {"width": 2}}))
    fig.update_layout(**{**_BASE, "hovermode": "closest"}, height=460,
                      title=f"{head}<br><sup>{tail + ' · ' if tail else ''}{tr.scenario} peak</sup>",
                      xaxis={"title": "cell in group", "showgrid": False},
                      yaxis={"title": "parallel group", "autorange": "reversed", "showgrid": False})
    return fig


def heat_range(results: list[DesignResult]) -> tuple[float, float]:
    """Min/max over the peak fields that `heatmap` shows, for a shared colour scale."""
    fields = [(r.charge if r.metrics["t_max_charge_c"] >= r.metrics["t_max_drive_c"] else r.drive).t_field_peak[0]
              for r in results]
    return float(min(f.min() for f in fields)), float(max(f.max() for f in fields))


def histogram(values: np.ndarray, metric: str, color: str) -> go.Figure:
    fig = go.Figure(go.Histogram(x=values, nbinsx=20, marker={"color": color}))
    fig.update_layout(**{**_BASE, "hovermode": "closest"}, height=320, bargap=0.05,
                      title=f"{METRICS[metric].label}<br><sup>mean {values.mean():.1f} · P5 "
                            f"{np.percentile(values, 5):.1f} · P95 {np.percentile(values, 95):.1f}</sup>",
                      xaxis_title=METRICS[metric].unit, yaxis_title="packs")
    return _axes(fig)


def validation(t_s: np.ndarray, measured: np.ndarray, predicted: np.ndarray, label: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=t_s / 60, y=measured, name="measured", mode="lines",
                             line={"color": MEASURED_COLOR, "width": 1.5}))
    fig.add_trace(go.Scatter(x=t_s / 60, y=predicted, name="model", mode="lines",
                             line={"color": DESIGN_COLORS[0], "width": 2, "dash": "dash"}))
    fig.update_layout(**_BASE, title=label, xaxis_title="time [min]", height=360, margin={"t": 48})
    return _axes(fig)
