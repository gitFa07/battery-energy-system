"""Fit cell-model parameters to measured test logs, using the *same* simulator as the design studies.

Log format (CSV, header required): time_s, current_a (+ = discharge), voltage_v, temp_c (surface)
and optionally temp_core_c (internal) and soc (reference SOC; its first value sets the initial SOC — otherwise the
first voltage is read as a rested OCV). One cell, or one parallel group (pass `parallel`).
With a soc column, voltage RMSE is also reported over the operating window SOC >= 10 % (`OP_SOC_MIN`).
An optional ambient_c column (first value used) sets the chamber temperature when the cell starts warmer than it,
e.g. a charge logged straight after a drive; otherwise ambient = first temp_c.

Free parameters (any subset, shared across all logs):
  r0_ohm, r1_ohm, tau_s, capacity_ah, h_eff_w_m2k   — always
  r_temp_k                                          — needs logs at two or more ambient temperatures
  ocv                                               — one voltage offset per OCV table point
  c_th_j_k                                          — heat capacity of cell + test fixture (test rig only)
h_eff_w_m2k and c_th_j_k describe the test rig (chamber, holder) and are never written to the cell.
Residuals are weighted by typical sensor noise. Each Jacobian is one batched simulation per log (base + perturbed
parameter sets as separate samples).

    python -m packforge.fit <log.csv> [<log.csv> ...] --cell nmc21700_5ah [--free r_temp_k ocv] [--save]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

from .loader import CELL_DIR, ROOT, load_cell
from .schema import Assumption, Cell, Design, Scenario
from .sim import State, build_pack, simulate

BASE = ("r0_ohm", "r1_ohm", "tau_s", "capacity_ah", "h_eff_w_m2k")
PARAMS = BASE  # default free set for a single log
V_NOISE, T_NOISE = 0.005, 0.3  # V, K — residual weights
REL_STEP, OCV_STEP, OCV_BOUND = 1e-3, 1e-4, 0.4
OP_SOC_MIN = 0.1  # packs are not run below this; the 1-RC model loses accuracy at the end of discharge
H_EFF_MAX = 300.0  # climate chambers with fans reach well above natural convection
VALIDATION_DIR = ROOT / "data" / "validation"


@dataclass
class Log:
    t_s: np.ndarray
    current_a: np.ndarray
    voltage_v: np.ndarray
    temp_c: np.ndarray
    temp_core_c: np.ndarray | None = None
    soc: np.ndarray | None = None  # reference SOC from the test rig (coulomb counting)
    name: str = ""
    ambient_c: float | None = None

    @property
    def soc0(self) -> float | None:
        return None if self.soc is None else float(self.soc[0])

    @classmethod
    def read(cls, path: Path) -> "Log":
        with path.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        col = lambda k: np.array([float(r[k]) for r in rows])  # noqa: E731
        has = rows[0].keys()
        return cls(col("time_s"), col("current_a"), col("voltage_v"), col("temp_c"),
                   col("temp_core_c") if "temp_core_c" in has else None,
                   col("soc") if "soc" in has else None, path.stem,
                   float(rows[0]["ambient_c"]) if "ambient_c" in has else None)


@dataclass
class LogFit:
    name: str
    t_s: np.ndarray
    v_pred: np.ndarray
    t_pred: np.ndarray
    v_rmse_mv: float
    t_rmse_k: float
    v_max_err_mv: float
    core_gap_k: float | None  # max measured core-minus-surface temperature (not modelled)
    v_rmse_op_mv: float | None = None  # over SOC >= OP_SOC_MIN (needs a soc column)


@dataclass
class FitResult:
    cell: Cell  # cell with fitted intrinsic parameters (OCV, R0, R1, tau, capacity, r_temp_k)
    h_eff: float  # test-rig cooling coefficient — describes the test chamber, not a pack
    fitted: dict[str, float]
    initial: dict[str, float]
    fits: list[LogFit] = field(default_factory=list)
    c_th: float | None = None  # test-rig heat capacity (cell + fixture), J/K, if fitted

    @property
    def v_rmse_mv(self) -> float:
        return float(np.sqrt(np.mean([f.v_rmse_mv ** 2 for f in self.fits])))

    @property
    def t_rmse_k(self) -> float:
        return float(np.sqrt(np.mean([f.t_rmse_k ** 2 for f in self.fits])))

    # single-log convenience (UI)
    t_s = property(lambda self: self.fits[0].t_s)
    v_pred = property(lambda self: self.fits[0].v_pred)
    t_pred = property(lambda self: self.fits[0].t_pred)


def bench_design(cell: Cell, parallel: int = 1) -> Design:
    """A bare cell (group) on the bench: no interconnect, no variation, protection opened to the cell limits."""
    return Design.model_validate({
        "id": "bench", "name": "bench", "cell": cell.model_dump(),
        "topology": {"series": 1, "parallel": parallel},
        "interconnect": {"cell_tab_resistance_ohm": 0, "string_resistance_ohm": 0, "busbar_ampacity_a": 1e3,
                         "fuse_rating_a": 1e3},
        "cooling": {"type": "passive", "h_eff_w_m2k": 8.0, "edge_factor": 1.0, "g_neighbor_w_k": 0.0},
        "sensing": {"n_temp_sensors": 1, "placement": "spread"},
        "bms": {"max_series": 1, "cost_inr": 0, "mass_kg": 0},
        "protection": {"ov_cell_v": cell.v_max + 0.5, "uv_cell_v": cell.v_min - 0.1, "ot_charge_c": 90,
                       "ot_discharge_c": 90, "oc_discharge_a": 1e3},
        "control": {"charge_c_rate": 0, "cv_v_cell": cell.v_max, "derate_start_c": 80, "derate_end_c": 90},
        "mechanical": {"holder_busbar_mass_per_cell_kg": 0, "enclosure_mass_kg": 0},
        "costs": {"holder_busbar_per_cell_inr": 0, "assembly_per_cell_inr": 0, "enclosure_inr": 0},
        "variation": {"capacity_sigma": 0, "r0_sigma": 0},
    })


def param_names(cell: Cell, free: tuple[str, ...], fixed: tuple[str, ...] = ()) -> list[str]:
    names = [n for n in BASE if n not in fixed] + [p for p in free if p in ("r_temp_k", "c_th_j_k")]
    if "ocv" in free:
        names += [f"ocv_{i}" for i in range(len(cell.ocv_v)) if f"ocv_{i}" not in fixed]
    return names


def initial_vector(cell: Cell, names: list[str], h_eff_guess: float) -> np.ndarray:
    start = {"h_eff_w_m2k": h_eff_guess, "c_th_j_k": cell.mass_kg * cell.cp_j_kgk} | {
        n: getattr(cell, n) for n in names if hasattr(cell, n)}
    return np.array([0.0 if n.startswith("ocv_") else float(start[n]) for n in names])


def apply(cell: Cell, names: list[str], x: np.ndarray, h_eff_default: float = 8.0) -> tuple[Cell, float]:
    """Cell with the fitted values written in, plus the test-rig h_eff."""
    vals = {"h_eff_w_m2k": h_eff_default} | dict(zip(names, map(float, x)))
    update = {k: v for k, v in vals.items() if k in ("r0_ohm", "r1_ohm", "tau_s", "capacity_ah", "r_temp_k")}
    offsets = [vals.get(f"ocv_{i}", 0.0) for i in range(len(cell.ocv_v))]
    update["ocv_v"] = [round(v + o, 4) for v, o in zip(cell.ocv_v, offsets)]
    return cell.model_copy(update=update), vals["h_eff_w_m2k"]


def predict(cell: Cell, x: np.ndarray, log: Log, parallel: int = 1, dt: float = 2.0,
            names: list[str] | tuple[str, ...] = BASE) -> tuple[np.ndarray, np.ndarray]:
    """Replay the logged current for each parameter row of `x` (N x len(names)) in one batched run.

    Returns voltage and surface temperature (N x len(log)) on the log's time base.
    """
    x = np.atleast_2d(x)
    names = list(names)
    pack = build_pack(bench_design(cell, parallel), n_samples=len(x))
    col = lambda j: x[:, j][:, None, None] * np.ones_like(pack.r0)  # noqa: E731
    for j, n in enumerate(names):
        if n == "h_eff_w_m2k":
            pack.g_sink = col(j) * cell.surface_m2
        elif n == "c_th_j_k":
            pack.c_th = col(j)
        elif n == "capacity_ah":
            pack.cap_ah = col(j)
        elif n in ("r0_ohm", "r1_ohm", "tau_s", "r_temp_k"):
            setattr(pack, {"r0_ohm": "r0", "r1_ohm": "r1"}.get(n, n), col(j))
        elif n.startswith("ocv_"):
            pack.ocv_v[:, int(n[4:])] += x[:, j]
    grid = np.arange(0, log.t_s[-1] + dt, dt)
    current = np.interp(grid, log.t_s, log.current_a)
    soc0 = log.soc0 if log.soc0 is not None else float(np.interp(log.voltage_v[0], cell.ocv_v, cell.ocv_soc))
    scenario = Scenario(type="current", start_soc=soc0, max_time_s=int(grid.size * dt),
                        profile=[(dt, float(i)) for i in current])
    start = np.full(pack.r0.shape, float(log.temp_c[0]))
    init = State(np.full(pack.r0.shape, soc0), np.zeros(pack.r0.shape), start, start.copy())
    ambient = float(log.temp_c[0]) if log.ambient_c is None else log.ambient_c
    tr = simulate(pack, scenario, ambient, "replay", dt, init)
    v = np.nan_to_num(tr.v_pack, nan=cell.v_min - 0.1).T  # a cut-off sample reads as collapsed voltage
    t = np.nan_to_num(tr.t_max, nan=float(log.temp_c[-1])).T
    interp = lambda y: np.array([np.interp(log.t_s, tr.t_s, row) for row in y])  # noqa: E731
    return interp(v), interp(t)


def evaluate(cell: Cell, h_eff: float, log: Log, parallel: int = 1, c_th: float | None = None) -> LogFit:
    """Predict one log with fixed parameters — used for hold-out checks. h_eff/c_th describe the test rig."""
    rig = {"h_eff_w_m2k": h_eff} | ({} if c_th is None else {"c_th_j_k": c_th})
    v, t = (y[0] for y in predict(cell, np.array([list(rig.values())]), log, parallel, names=list(rig)))
    err = v - log.voltage_v
    gap = float(np.max(log.temp_core_c - log.temp_c)) if log.temp_core_c is not None else None
    op = None if log.soc is None else float(np.sqrt(np.mean(err[log.soc >= OP_SOC_MIN] ** 2)) * 1000)
    return LogFit(log.name, log.t_s, v, t, float(np.sqrt(np.mean(err ** 2)) * 1000),
                  float(np.sqrt(np.mean((t - log.temp_c) ** 2))), float(np.max(np.abs(err)) * 1000), gap, op)


def fit_logs(logs: list[Log], cell: Cell, free: tuple[str, ...] = (), h_eff_guess: float = 8.0,
             parallel: int = 1, fixed: tuple[str, ...] = ()) -> FitResult:
    """Fit shared parameters to all logs. `fixed` keeps parameters (base names or `ocv_<i>`) at the starting
    cell's values."""
    names = param_names(cell, free, fixed)
    x0 = initial_vector(cell, names, h_eff_guess)
    is_ocv = np.array([n.startswith("ocv_") for n in names])
    lo = np.where(is_ocv, -OCV_BOUND, x0 * 0.2)
    hi = np.where(is_ocv, OCV_BOUND, np.where(np.array(names) == "h_eff_w_m2k", H_EFF_MAX, x0 * 5))
    scale = np.where(is_ocv, 0.01, np.abs(x0))

    def residuals_batch(xs: np.ndarray) -> np.ndarray:
        parts = []
        for log in logs:
            v, t = predict(cell, xs, log, parallel, names=names)
            parts += [(v - log.voltage_v) / V_NOISE, (t - log.temp_c) / T_NOISE]
        return np.hstack(parts)

    def jac(x: np.ndarray) -> np.ndarray:
        steps = np.where(is_ocv, OCV_STEP, REL_STEP * np.abs(x))
        rows = residuals_batch(np.vstack([x, x + np.diag(steps)]))
        return ((rows[1:] - rows[0]) / steps[:, None]).T

    sol = least_squares(lambda x: residuals_batch(x)[0], x0, jac=jac, bounds=(lo, hi), x_scale=scale)
    fitted_cell, h_eff = apply(cell, names, sol.x)
    c_th = float(sol.x[names.index("c_th_j_k")]) if "c_th_j_k" in names else None
    return FitResult(fitted_cell, h_eff, dict(zip(names, map(float, sol.x))), dict(zip(names, map(float, x0))),
                     [evaluate(fitted_cell, h_eff, log, parallel, c_th) for log in logs], c_th)


def fit(log: Log, cell: Cell, h_eff_guess: float = 8.0, parallel: int = 1) -> FitResult:
    """Single-log fit of the base parameters."""
    return fit_logs([log], cell, (), h_eff_guess, parallel)


def load_calibration(cell_id: str) -> dict | None:
    """Calibration record written by scripts/calibrate_<cell>.py (fit + hold-out results), if the cell has one."""
    path = VALIDATION_DIR / f"calibration_{cell_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def save_fitted_cell(res: FitResult, log_paths: list[Path]) -> Path:
    """Write `<cell>_fitted.json` so a design can switch to measured parameters by changing its `cell` id."""
    c, names = res.cell, ", ".join(p.name for p in log_paths)
    out = c.model_copy(update={
        "id": f"{c.id}_fitted", "name": f"{c.name} (fitted)",
        "sources": c.sources + [f"Fitted to {names} (V RMSE {res.v_rmse_mv:.1f} mV, T RMSE {res.t_rmse_k:.2f} K)"],
        "assumptions": c.assumptions + [Assumption(
            id=f"{c.id.upper()}-FIT", source=names, affects=["cell", "electrical", "thermal"],
            text="Fitted parameters supersede the datasheet values above; valid over the logs' temperature and "
                 "current range only")],
    })
    path = CELL_DIR / f"{out.id}.json"
    path.write_text(json.dumps(out.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="packforge.fit")
    ap.add_argument("logs", type=Path, nargs="+")
    ap.add_argument("--cell", required=True, help="cell id in data/cells to start from")
    ap.add_argument("--free", nargs="*", default=[], choices=["r_temp_k", "ocv"], help="extra free parameters")
    ap.add_argument("--parallel", type=int, default=1)
    ap.add_argument("--save", action="store_true", help="write data/cells/<cell>_fitted.json")
    args = ap.parse_args()

    res = fit_logs([Log.read(p) for p in args.logs], load_cell(args.cell), tuple(args.free), parallel=args.parallel)
    print(f"{'param':<14}{'start':>12}{'fitted':>12}")
    for k in res.fitted:
        print(f"{k:<14}{res.initial[k]:>12.4g}{res.fitted[k]:>12.4g}")
    for f in res.fits:
        print(f"{f.name}: V RMSE {f.v_rmse_mv:.1f} mV (max {f.v_max_err_mv:.0f}) · T RMSE {f.t_rmse_k:.2f} K")
    if args.save:
        print(f"saved {save_fitted_cell(res, args.logs)}")


if __name__ == "__main__":
    main()
