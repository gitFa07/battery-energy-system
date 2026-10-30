"""Convert TU Berlin "Lithium-Ion Battery Internal Temperature Dataset" drive-cycle files to the fit log format.

Source: Yao, Droese, Kowal (2026), DOI 10.14279/depositonce-25110, CC BY 4.0. Changes made here: current sign
flipped to + = discharge, columns renamed, values rounded. Surface temperature -> temp_c, internal -> temp_core_c.

`convert_charges` cuts the CC-CV charges (4.93 A ~ 1C to 4.2 V) that follow each drive cycle, plus the 2 h rest
after them, out of the raw test files (`0_raw/*.parquet`; columns by position: Testtime, StepID, Voltage, Current
[+ = charge], Temperature2 = surface, Temperature3 = internal — identified by matching the publishers'
preprocessed Outer_temp/Inner_temp (residual sd 0.08-0.10 K); Temperature4 is another probe, absent on cell 105).
Resampled to 1 s. The charge starts right after the
drive hit 2.5 V, so soc starts at 0 and the cell starts warmer than the chamber; ambient_c is the surface reading at
the end of the rest (cell and chamber in equilibrium, which also cancels the sensors' offset).

    python scripts/convert_tuberlin.py <raw 2_preprocessed dir> <cell> <temp_c> <cycle> [<cycle> ...]
    e.g. python scripts/convert_tuberlin.py data/raw/tuberlin_internal_temp/2_preprocessed AM23NMC00103 25 US06
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

from packforge.loader import ROOT

OUT_DIR = ROOT / "data" / "validation"


def find(raw: Path, cell: str, temp_c: int, cycle: str) -> Path:
    folder = raw / cell / f"{cell}_std_{temp_c:02d}deg"
    hits = [p for p in folder.glob("*.csv") if p.name.split("_")[1] == cycle]
    if len(hits) != 1:
        raise FileNotFoundError(f"{cycle} not found (or ambiguous) in {folder}")
    return hits[0]


def convert(src: Path, dst: Path) -> int:
    with src.open(encoding="utf-8") as f_in, dst.open("w", newline="", encoding="utf-8") as f_out:
        w = csv.writer(f_out)
        w.writerow(["time_s", "current_a", "voltage_v", "temp_c", "temp_core_c", "soc"])
        n = 0
        for r in csv.DictReader(f_in):
            w.writerow([f"{float(r['Time']):.0f}", f"{-float(r['Current']):.4f}", f"{float(r['Voltage']):.4f}",
                        f"{float(r['Outer_temp']):.3f}", f"{float(r['Inner_temp']):.3f}", f"{float(r['SOC']):.5f}"])
            n += 1
    return n


CYCLE_ORDER = ("BCDC", "LA92", "HHDDT", "CSHVC", "FTP-72", "FTP-75", "HWFET", "IM", "US06", "PDTCB", "PDMHC", "OCTBC")


def convert_charges(parquet: Path, cell: str, temp_c: int, out_dir: Path) -> list[Path]:
    """One log per charge-after-drive, named TUB_M50LT_<cell>_CHG-<preceding cycle>_<T>C.csv."""
    import pandas as pd

    raw = pd.read_parquet(parquet)
    t, step, v, i = (raw.iloc[:, k].to_numpy(float) for k in (1, 2, 4, 5))
    surf, core = raw.iloc[:, 7].to_numpy(float), raw.iloc[:, 8].to_numpy(float)
    edges = np.flatnonzero(np.diff(step)) + 1
    segs = list(zip(np.r_[0, edges], np.r_[edges, step.size]))
    drives = [k for k, (a, b) in enumerate(segs) if i[a:b].min() < -1]  # drive cycles discharge at up to ~2C
    out = []
    for n, k in enumerate(drives):
        if k + 2 >= len(segs) or n >= len(CYCLE_ORDER):
            continue
        (a, _), (_, b) = segs[k + 1], segs[k + 2]  # charge step + the rest after it
        if not (i[a:segs[k + 1][1]].min() >= 0 and v[segs[k + 1][1] - 1] > 4.19):
            continue  # not a full CC-CV charge (e.g. the final storage charge)
        grid = np.arange(0, t[b - 1] - t[a], 1.0)
        tt = t[a:b] - t[a]
        cur = np.interp(grid, tt, -i[a:b])
        soc = np.clip(np.cumsum(-cur) / 3600 / (np.sum(-cur) / 3600), 0, 1)
        dst = out_dir / f"TUB_M50LT_{cell}_CHG-{CYCLE_ORDER[n]}_{temp_c}C.csv"
        with dst.open("w", newline="", encoding="utf-8") as f_out:
            w = csv.writer(f_out)
            w.writerow(["time_s", "current_a", "voltage_v", "temp_c", "temp_core_c", "soc", "ambient_c"])
            amb = f"{surf[b - 1]:.3f}"
            for row in zip(grid, cur, np.interp(grid, tt, v[a:b]), np.interp(grid, tt, surf[a:b]),
                           np.interp(grid, tt, core[a:b]), soc):
                w.writerow([f"{row[0]:.0f}", f"{row[1]:.4f}", f"{row[2]:.4f}", f"{row[3]:.3f}", f"{row[4]:.3f}",
                            f"{row[5]:.5f}", amb])
        out.append(dst)
    return out


def out_path(cell: str, temp_c: int, cycle: str) -> Path:
    return OUT_DIR / f"TUB_M50LT_{cell}_{cycle}_{temp_c}C.csv"


def main() -> None:
    raw, cell, temp_c, cycles = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]), sys.argv[4:]
    for cycle in cycles:
        dst = out_path(cell, temp_c, cycle)
        print(f"{dst.name}: {convert(find(raw, cell, temp_c, cycle), dst)} rows")


if __name__ == "__main__":
    main()
