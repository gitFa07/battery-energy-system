"""Time-domain electro-thermal simulation of a cell group / pack with its BMS control loop.

Model (per cell, vectorised over a batch of N sampled packs, S series groups, P parallel cells):
  electrical  V = OCV(SOC) - V_rc - I*R0,  1-RC branch, R0/R1 scale with Arrhenius(T)
              parallel cells share terminal voltage; series groups share current
  thermal     C dT/dt = I^2 R0 + V_rc^2/R1 - G_sink (T - T_sink) + G_nb * sum(neighbour dT)
  control     CC-CV charge with derating on the BMS's view of the hotspot: either its hottest NTC, or an
              on-board observer (nominal-parameter copy of the thermal network, corrected by the NTCs)
  protection  OV / UV / OT trips end the scenario (OT always acts on real sensors only). A pack plugged in
              too hot is held at zero current until derating releases it — a hold, not a trip.
Sign convention: current > 0 is discharge.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .schema import Design, Scenario

T_REF_K = 298.15
TAIL_SLOPE_V = 10.0  # V per unit SOC beyond empty/full
OBS_CORRECTION_PER_S = 0.02  # observer pull towards the NTC readings


@dataclass
class Pack:
    """Per-cell parameter arrays for a batch of sampled packs (shape N x S x P)."""

    design: Design
    cap_ah: np.ndarray
    r0: np.ndarray
    r1: np.ndarray
    tau_s: np.ndarray
    r_temp_k: np.ndarray  # Arrhenius coefficient of R0/R1, per sample
    ocv_v: np.ndarray  # (N, K) OCV table values at the cell's ocv_soc points, per sample
    g_sink: np.ndarray  # (S, P) or (N, S, P) W/K
    sensor_rows: np.ndarray
    sensor_cols: np.ndarray
    c_th: np.ndarray | None = None  # per-cell heat capacity J/K; None = cell mass x cp (fit: + test-rig fixture)

    @property
    def n(self) -> int:
        return self.cap_ah.shape[0]


def sensor_positions(design: Design) -> tuple[np.ndarray, np.ndarray]:
    s, p = design.topology.series, design.topology.parallel
    n = min(design.sensing.n_temp_sensors, s * p)
    placement = design.sensing.placement
    if isinstance(placement, list):
        rows, cols = zip(*placement)
        return np.clip(np.array(rows), 0, s - 1), np.clip(np.array(cols), 0, p - 1)
    if placement == "edge":
        perimeter = [(0, c) for c in range(p)] + [(r, p - 1) for r in range(1, s)]
        perimeter += [(s - 1, c) for c in range(p - 2, -1, -1)] + [(r, 0) for r in range(s - 2, 0, -1)]
        idx = np.linspace(0, len(perimeter) - 1, n, endpoint=n == 1).round().astype(int)
        rows, cols = zip(*(perimeter[i] for i in idx))
        return np.array(rows), np.array(cols)
    if placement == "center":
        flat = np.argsort(np.hypot(*np.meshgrid(np.arange(s) - (s - 1) / 2, np.arange(p) - (p - 1) / 2,
                                                indexing="ij")).ravel(), kind="stable")[:n]
    else:  # spread: evenly over the grid, avoiding the extreme corners
        flat = np.linspace(0, s * p - 1, n + 2)[1:-1].round().astype(int)
    return flat // p, flat % p


def build_pack(design: Design, n_samples: int = 1, seed: int | None = None) -> Pack:
    s, p = design.topology.series, design.topology.parallel
    var = design.variation
    rng = np.random.default_rng(var.seed if seed is None else seed)
    shape = (n_samples, s, p)
    cap_f = np.clip(1 + rng.normal(0, var.capacity_sigma, shape), 0.8, 1.2)
    r_f = np.clip(1 + rng.normal(0, var.r0_sigma, shape), 0.7, 1.5)
    cell = design.cell
    g = np.full((s, p), design.cooling.h_eff_w_m2k * cell.surface_m2)
    edge = np.zeros((s, p), dtype=bool)
    edge[[0, -1], :] = True
    edge[:, [0, -1]] = True
    g[edge] *= design.cooling.edge_factor
    rows, cols = sensor_positions(design)
    return Pack(
        design=design,
        cap_ah=cell.capacity_ah * cap_f,
        r0=(cell.r0_ohm + design.interconnect.cell_tab_resistance_ohm) * r_f,
        r1=cell.r1_ohm * r_f,
        tau_s=np.full(shape, cell.tau_s),
        r_temp_k=np.full(shape, cell.r_temp_k),
        ocv_v=np.tile(np.array(cell.ocv_v), (n_samples, 1)),
        g_sink=g,
        sensor_rows=rows,
        sensor_cols=cols,
    )


@dataclass
class State:
    """Per-cell state carried between chained scenarios (each N x S x P)."""

    soc: np.ndarray
    v_rc: np.ndarray
    temp: np.ndarray
    obs: np.ndarray  # BMS observer's temperature estimate


@dataclass
class Trace:
    """Recorded time series (steps x N) plus per-sample end information."""

    scenario: str
    t_s: np.ndarray
    current_a: np.ndarray
    v_pack: np.ndarray
    v_cell_min: np.ndarray
    v_cell_max: np.ndarray
    soc_mean: np.ndarray
    t_max: np.ndarray
    t_min: np.ndarray
    t_mean: np.ndarray
    t_sensed_max: np.ndarray
    t_bms_hot: np.ndarray  # what the BMS believes the hottest cell is (drives derating)
    heat_w_mean: np.ndarray
    cell_current_max: np.ndarray
    end_step: np.ndarray
    end_reason: list[str]
    t_field_peak: np.ndarray  # (N, S, P) temperature field when T_max peaked
    final: State
    events: list[list[str]] = field(default_factory=list)


def _laplacian(t: np.ndarray) -> np.ndarray:
    lap = np.zeros_like(t)
    d = t[:, 1:, :] - t[:, :-1, :]
    lap[:, :-1, :] += d
    lap[:, 1:, :] -= d
    d = t[:, :, 1:] - t[:, :, :-1]
    lap[:, :, :-1] += d
    lap[:, :, 1:] -= d
    return lap


def _interp_rows(x: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """Piecewise-linear lookup of x (N, S, P) in a table with shared xs (K,) and per-sample ys (N, K)."""
    xc = np.clip(x, xs[0], xs[-1])
    k = np.clip(np.searchsorted(xs, xc, side="right") - 1, 0, len(xs) - 2)
    w = (xc - xs[k]) / (xs[k + 1] - xs[k])
    rows = np.arange(ys.shape[0])[:, None, None]
    return ys[rows, k] * (1 - w) + ys[rows, k + 1] * w


def _profile_series(profile: list[tuple[float, float]], steps: int, dt: float) -> np.ndarray:
    """Sample a repeating [duration, value] profile at every step."""
    ends = np.cumsum([dur for dur, _ in profile])
    t = (np.arange(steps) * dt) % ends[-1]
    return np.array([v for _, v in profile])[np.searchsorted(ends, t, side="right")]


def simulate(pack: Pack, scenario: Scenario, ambient_c: float, name: str = "", dt: float = 2.0,
             init: State | None = None) -> Trace:
    """Run one scenario. `init` continues from a previous scenario's end state (e.g. charge after a ride)."""
    d = pack.design
    cell, ctrl, prot, cool = d.cell, d.control, d.protection, d.cooling
    n, s, p = pack.cap_ah.shape
    xs = np.array(cell.ocv_soc)
    c_nom = cell.mass_kg * cell.cp_j_kgk
    c_th = c_nom if pack.c_th is None else pack.c_th
    t_sink = ambient_c if cool.sink_temp_c is None else cool.sink_temp_c
    exp_tau = np.exp(-dt / pack.tau_s)
    q_nom = d.capacity_ah
    charging = scenario.type == "charge"
    if not charging and not scenario.profile:
        raise ValueError(f"{scenario.type} scenario '{name}' needs a profile")

    if init is None:
        soc = np.full((n, s, p), scenario.start_soc)
        v_rc = np.zeros((n, s, p))
        temp = np.full((n, s, p), float(ambient_c))
        obs = temp.copy()
    else:
        soc, v_rc, temp, obs = (x.copy() for x in (init.soc, init.v_rc, init.temp, init.obs))
    obs_g_sink = pack.g_sink * (1 + ctrl.observer_h_error)
    r_nom0, r_nom1 = cell.r0_ohm + d.interconnect.cell_tab_resistance_ohm, cell.r1_ohm
    active = np.ones(n, dtype=bool)
    end_step = np.full(n, -1)
    end_reason = ["timeout"] * n
    events: list[list[str]] = [[] for _ in range(n)]
    steps = int(scenario.max_time_s / dt)
    series = None if charging else _profile_series(scenario.profile, steps, dt)

    rec = {k: np.full((steps, n), np.nan) for k in (
        "current_a", "v_pack", "v_cell_min", "v_cell_max", "soc_mean", "t_max", "t_min", "t_mean",
        "t_sensed_max", "t_bms_hot", "heat_w_mean", "cell_current_max")}
    peak_t = np.full(n, -np.inf)
    prev_i = np.zeros(n)
    started = np.zeros(n, dtype=bool)
    t_field_peak = temp.copy()

    def stop(mask: np.ndarray, reason: str, k: int) -> None:
        if not mask.any():
            return
        for i in np.flatnonzero(mask & active):
            end_step[i], end_reason[i] = k, reason
            events[i].append(f"t={k * dt / 60:.1f} min: {reason}")
        active[mask] = False

    for k in range(steps):
        if not active.any():
            break
        arr = np.exp(pack.r_temp_k * (1 / (temp + 273.15) - 1 / T_REF_K))
        r0, r1 = pack.r0 * arr, pack.r1 * arr
        # steep tails beyond 0/100% SOC so an over-drained or over-charged cell reaches UV/CV instead of plateauing
        ocv = _interp_rows(soc, xs, pack.ocv_v) + TAIL_SLOPE_V * (np.minimum(soc, 0) + np.maximum(soc - 1, 0))
        g = 1 / r0
        a = ((ocv - v_rc) * g).sum(-1) / g.sum(-1)  # group open-circuit-equivalent voltage (N,S)
        b = 1 / g.sum(-1)  # group resistance (N,S)
        sensors = temp[:, pack.sensor_rows, pack.sensor_cols]
        sensed = sensors.max(-1)
        # observer: pull the estimate towards the NTCs, then take its hotspot (never below a real reading)
        pull = (sensors - obs[:, pack.sensor_rows, pack.sensor_cols]).mean(-1) * active
        obs += OBS_CORRECTION_PER_S * dt * pull[:, None, None]
        bms_hot = np.maximum(sensed, obs.max(axis=(1, 2))) if ctrl.derate_on == "observer" else sensed

        if charging:
            stop((sensed > prot.ot_charge_c) & (prev_i < 0), "OT trip (charge)", k)
            span = max(ctrl.derate_end_c - ctrl.derate_start_c, 1e-6)
            derate = np.clip((ctrl.derate_end_c - bms_hot) / span, 0, 1)
            i_cc = -ctrl.charge_c_rate * q_nom * derate
            i_cv = ((a - ctrl.cv_v_cell) / b).max(-1)
            current = np.minimum(np.maximum(i_cc, i_cv), 0.0)
            in_cv = i_cv > i_cc
            stop(in_cv & (-current < ctrl.cutoff_c_rate * q_nom), "CV complete", k)
        elif scenario.type == "drive":
            power = series[k] + cool.parasitic_w
            r_tot = b.sum(-1) + d.interconnect.string_resistance_ohm
            disc = a.sum(-1) ** 2 - 4 * r_tot * power
            stop(disc < 0, "power limit", k)
            current = (a.sum(-1) - np.sqrt(np.maximum(disc, 0))) / (2 * r_tot)
            stop(sensed > prot.ot_discharge_c, "OT trip (discharge)", k)
        else:  # imposed current, e.g. replaying a measured test log
            current = np.full(n, series[k])

        current = np.where(active, current, 0.0)
        v_grp = a - b * current[:, None]
        stop(v_grp.max(-1) > prot.ov_cell_v + 1e-6, "OV trip", k)
        stop(v_grp.min(-1) < prot.uv_cell_v, "UV cutoff", k)
        current = np.where(active, current, 0.0)
        v_grp = a - b * current[:, None]
        i_cell = (ocv - v_rc - v_grp[..., None]) * g
        if charging:
            for i in np.flatnonzero((current < 0) & ~started & (k > 0)):
                events[i].append(f"t={k * dt / 60:.1f} min: charging released after thermal hold")
            started |= current < 0
        prev_i = current

        heat = (i_cell**2 * r0 + v_rc**2 / r1) * cell.heat_factor
        tmax = temp.max(axis=(1, 2))
        newpeak = tmax > peak_t
        peak_t = np.where(newpeak, tmax, peak_t)
        t_field_peak[newpeak] = temp[newpeak]

        for key, val in (
            ("current_a", current),
            ("v_pack", v_grp.sum(-1) - current * d.interconnect.string_resistance_ohm),
            ("v_cell_min", v_grp.min(-1)),
            ("v_cell_max", v_grp.max(-1)),
            ("soc_mean", soc.mean(axis=(1, 2))),
            ("t_max", tmax),
            ("t_min", temp.min(axis=(1, 2))),
            ("t_mean", temp.mean(axis=(1, 2))),
            ("t_sensed_max", sensed),
            ("t_bms_hot", bms_hot),
            ("heat_w_mean", heat.mean(axis=(1, 2))),
            ("cell_current_max", np.abs(i_cell).max(axis=(1, 2))),
        ):
            rec[key][k] = np.where(active, val, np.nan)

        # finished samples are frozen so their end state can seed a chained scenario
        live = active[:, None, None]
        soc = np.where(live, soc - i_cell * dt / (3600 * pack.cap_ah), soc)
        v_rc = np.where(live, v_rc * exp_tau + r1 * i_cell * (1 - exp_tau), v_rc)
        temp = np.where(live, temp + dt / c_th * (
            heat - pack.g_sink * (temp - t_sink) + cool.g_neighbor_w_k * _laplacian(temp)), temp)
        # observer knows only the pack current: equal sharing, nominal resistance, steady-state RC heat
        arr_obs = np.exp(cell.r_temp_k * (1 / (obs + 273.15) - 1 / T_REF_K))
        heat_obs = (current / p)[:, None, None] ** 2 * (r_nom0 + r_nom1) * arr_obs
        obs = np.where(live, obs + dt / c_nom * (
            heat_obs - obs_g_sink * (obs - t_sink) + cool.g_neighbor_w_k * _laplacian(obs)), obs)

    last = k + 1
    end_step = np.where(end_step < 0, last, end_step)
    for i in np.flatnonzero(active):
        events[i].append(f"t={last * dt / 60:.1f} min: timeout")
    return Trace(
        scenario=name or scenario.type,
        t_s=np.arange(last) * dt,
        **{key: val[:last] for key, val in rec.items()},
        end_step=end_step,
        end_reason=end_reason,
        t_field_peak=t_field_peak,
        final=State(soc, v_rc, temp, obs),
        events=events,
    )
