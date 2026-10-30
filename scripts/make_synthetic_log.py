"""Generate a SYNTHETIC pulse-test log to check that `packforge.fit` recovers known parameters.

This is a method check, not evidence: the "measurement" comes from our own model with chosen "true"
parameters plus sensor noise. Replace it with a rig or public-dataset log for real validation.

    python scripts/make_synthetic_log.py
"""

from __future__ import annotations

import csv

import numpy as np

from packforge.fit import PARAMS, Log, predict
from packforge.loader import ROOT, load_cell

TRUE = {"r0_ohm": 0.026, "r1_ohm": 0.009, "tau_s": 45.0, "capacity_ah": 4.85}
TRUE_H = 9.0
OUT = ROOT / "data" / "validation" / "SYNTHETIC_nmc21700_pulse.csv"


def pulse_profile(cap_ah: float) -> list[tuple[float, float]]:
    """Rest, then repeated [1C 10 s pulse, 40 s rest, 0.5C for ~8 % SOC, 5 min rest] down to ~10 % SOC."""
    seg = [(120, 0.0)]
    for _ in range(10):
        seg += [(10, cap_ah), (40, 0.0), (600, 0.5 * cap_ah), (300, 0.0)]
    return seg


def main() -> None:
    cell = load_cell("nmc21700_5ah_uncalibrated")  # generic class values; the calibrated cell has its own OCV
    x_true = np.array([TRUE[k] for k in PARAMS[:4]] + [TRUE_H])
    seg = pulse_profile(5.0)
    t = np.arange(0, sum(d for d, _ in seg), 1.0)
    ends = np.cumsum([d for d, _ in seg])
    current = np.array([i for _, i in seg])[np.searchsorted(ends, t, side="right")]
    v0 = float(np.interp(0.98, cell.ocv_soc, cell.ocv_v))  # rested at 98 % SOC
    v, temp = (y[0] for y in predict(cell, x_true, Log(t, current, np.full_like(t, v0), np.full_like(t, 25.0)), dt=1.0))
    rng = np.random.default_rng(42)
    v_meas = v + rng.normal(0, 0.003, t.size)  # INA226-class voltage noise
    t_meas = np.round((temp + rng.normal(0, 0.15, t.size)) / 0.0625) * 0.0625  # DS18B20 resolution
    keep = slice(None, None, 2)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time_s", "current_a", "voltage_v", "temp_c"])
        for row in zip(t[keep], current[keep], v_meas[keep], t_meas[keep]):
            w.writerow([f"{row[0]:.0f}", f"{row[1]:.3f}", f"{row[2]:.4f}", f"{row[3]:.4f}"])
    print(f"wrote {OUT} ({t[keep].size} rows); true params {TRUE}, h_eff {TRUE_H}")


if __name__ == "__main__":
    main()
