"""Replay a real measured log through VoltTwin's datasheet cell model — the empirical side of the validation.

Logs: TU Berlin LG M50LT internal-temperature dataset (CC BY 4.0, data/validation/SOURCES.md) — a *proxy* for the
generic NMC 21700 class cell, not the design cell. VoltTwin's cell is NOT fitted to these logs:
    V = OCV_NMC(soc_log) − I · R0 · (1 + margin)                  (soc from the log's coulomb count)
    C_rig dT/dt = I² R + I·T·dU/dT·(−1) − h A (T − T_amb)          (one node, cell in a climate chamber)
Only the chamber h and rig heat capacity come from the PackForge calibration record (test-rig parameters fitted at
25/35 °C, never used for packs); at 45 °C the logs are hold-out for those too. The LFP cell has no log: not validated.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import ROOT
from src.models.schemas import CellSpec
from src.physics.electrical import BOL_R_MARGIN, ocv
from src.physics.thermal import ENTROPIC_V_K

VALIDATION_DIR = ROOT / "data" / "validation"
CALIBRATION = VALIDATION_DIR / "calibration_nmc21700_5ah.json"
SOC_OP_MIN = 0.10          # RMSE is also reported on the operating window (OCV tails dominate below 10 %)
RESAMPLE_S = 5


def real_logs() -> list[Path]:
    """Measured logs only — SYNTHETIC_* files are model-generated and never offered as evidence."""
    return sorted(p for p in VALIDATION_DIR.glob("TUB_*.csv"))


def rig_parameters() -> tuple[float, float]:
    rec = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    return float(rec["chamber_h_eff_w_m2k"]), float(rec["rig_c_th_j_k"])


@dataclass
class Replay:
    log: str
    t_s: np.ndarray
    current_a: np.ndarray
    soc: np.ndarray
    v_meas: np.ndarray
    v_pred: np.ndarray
    t_meas: np.ndarray        # surface
    t_core_meas: np.ndarray
    t_pred: np.ndarray
    ambient_c: float
    v_rmse_mv: float
    v_rmse_op_mv: float
    t_rmse_k: float
    t_rise_meas_k: float
    t_rise_pred_k: float

    @property
    def label(self) -> str:
        parts = self.log.removesuffix(".csv").split("_")
        return f"{parts[-2]} @ {parts[-1]}"


def replay_log(path: Path, cell: CellSpec) -> Replay:
    if cell.chemistry != "NMC":
        raise ValueError("only NMC has measured proxy logs; the LFP cell is not validated")
    df = pd.read_csv(path)
    df = df.iloc[::RESAMPLE_S].reset_index(drop=True)
    t = df["time_s"].to_numpy(float)
    i = df["current_a"].to_numpy(float)
    soc = df["soc"].to_numpy(float)
    r = cell.r0_ohm * (1 + BOL_R_MARGIN)
    v_pred = ocv("NMC", soc) - i * r

    h, c_rig = rig_parameters()
    area = math.pi * cell.diameter_mm / 1000 * cell.height_mm / 1000 + 2 * math.pi * (cell.diameter_mm / 2000) ** 2
    amb = float(df["ambient_c"].iloc[0]) if "ambient_c" in df else float(df["temp_c"].iloc[0])
    t_meas = df["temp_c"].to_numpy(float)
    temp = np.empty_like(t)
    temp[0] = t_meas[0]
    dts = np.diff(t, prepend=t[0])
    for k in range(1, len(t)):
        tk = temp[k - 1]
        q = i[k - 1] ** 2 * r - i[k - 1] * (tk + 273.15) * ENTROPIC_V_K["NMC"]
        temp[k] = tk + (q - h * area * (tk - amb)) * dts[k] / c_rig

    v_meas = df["voltage_v"].to_numpy(float)
    err = v_pred - v_meas
    op = soc >= SOC_OP_MIN
    return Replay(
        log=path.name, t_s=t, current_a=i, soc=soc, v_meas=v_meas, v_pred=v_pred, t_meas=t_meas,
        t_core_meas=df["temp_core_c"].to_numpy(float) if "temp_core_c" in df else t_meas, t_pred=temp,
        ambient_c=amb,
        v_rmse_mv=float(np.sqrt(np.mean(err**2)) * 1000),
        v_rmse_op_mv=float(np.sqrt(np.mean(err[op] ** 2)) * 1000) if op.any() else float("nan"),
        t_rmse_k=float(np.sqrt(np.mean((temp - t_meas) ** 2))),
        t_rise_meas_k=float(t_meas.max() - t_meas[0]),
        t_rise_pred_k=float(temp.max() - temp[0]),
    )
