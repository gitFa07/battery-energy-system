"""Plotly figures shared by the UI and the HTML report."""

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


def radar(results: list[DesignResult], study: Study) -> go.Figure:
    weights = study.score_weights
    labels = [METRICS[m].label for m in weights]
    fig = go.Figure()
    for r in results:
        vals = []
        for m, w in weights.items():
            col = [x.metrics[m] for x in results]
            lo, hi = np.nanmin(col), np.nanmax(col)
            v = 0.5 if hi == lo else (r.metrics[m] - lo) / (hi - lo)
            vals.append(v if w > 0 else 1 - v)
        fig.add_trace(go.Scatterpolar(r=vals + vals[:1], theta=labels + labels[:1], fill="toself", name=r.design.name))
    fig.update_layout(title="Relative trade-off (outer = better)", polar={"radialaxis": {"range": [0, 1]}}, height=450)
    return fig


def timeseries(results: list[DesignResult], scenario: str, label: str) -> go.Figure:
    fig = go.Figure()
    for r in results:
        tr = getattr(r, scenario)
        fig.add_trace(go.Scatter(x=tr.t_s / 60, y=getattr(tr, SIGNALS[label])[:, 0], name=r.design.name, mode="lines"))
    fig.update_layout(title=f"{label} — {scenario}", xaxis_title="time [min]", height=320, margin={"t": 40})
    return fig


def heatmap(r: DesignResult) -> go.Figure:
    tr = r.charge if r.metrics["t_max_charge_c"] >= r.metrics["t_max_drive_c"] else r.drive
    rows, cols = sensor_positions(r.design)
    fig = go.Figure(go.Heatmap(z=tr.t_field_peak[0], colorscale="Inferno", colorbar={"title": "°C"}))
    fig.add_trace(go.Scatter(x=cols, y=rows, mode="markers", showlegend=False,
                             marker={"size": 12, "symbol": "circle-open", "color": "cyan", "line": {"width": 2}}))
    fig.update_layout(title=f"{r.design.name}<br><sup>{tr.scenario} peak · rows = series groups · ◯ = NTC</sup>",
                      height=450, yaxis={"autorange": "reversed"})
    return fig


def validation(t_s: np.ndarray, measured: np.ndarray, predicted: np.ndarray, label: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=t_s / 60, y=measured, name="measured", mode="lines"))
    fig.add_trace(go.Scatter(x=t_s / 60, y=predicted, name="model", mode="lines", line={"dash": "dash"}))
    fig.update_layout(title=label, xaxis_title="time [min]", height=320, margin={"t": 40})
    return fig
