"""Calibrate the generic "NMC 21700 5 Ah class" cell on the LG M50LT proxy cell, then run the hold-out check.

Fit (cell AM23NMC00103 at 25 °C and 35 °C): US06 (dynamic discharge), HWFET (sustained discharge) and the 1C CC-CV
charge that follows US06 -> R0, R1, tau, r_temp_k and the OCV table; capacity fixed to the measured discharged
charge. Hold-out at 45 °C — a temperature not used in the fit — on 3 cells: the 10 other drive cycles and the 10
other charges. Only cell-intrinsic parameters are written to the cell; the fitted h_eff and heat capacity describe the climate
chamber and the cell's fixture and are kept in the calibration record only.

    python scripts/calibrate_nmc.py      (needs data/raw/tuberlin_internal_temp/dataset.zip, see data/validation/SOURCES.md)
"""

from __future__ import annotations

import json
import shutil
import sys
import zipfile
from pathlib import Path

import numpy as np

from convert_tuberlin import convert, convert_charges, find, out_path
from packforge.fit import OP_SOC_MIN, Log, evaluate, fit_logs
from packforge.loader import CELL_DIR, ROOT, load_cell
from packforge.schema import Assumption

DATA = ROOT / "data" / "raw" / "tuberlin_internal_temp"
PRE, PARQUET, HOLDOUT_DIR, CHARGE_DIR = (DATA / d for d in ("2_preprocessed", "raw_parquet", "converted", "charges"))
VALIDATION = ROOT / "data" / "validation"
CELL_ID = "nmc21700_5ah"
RECORD = VALIDATION / f"calibration_{CELL_ID}.json"
FIT_CYCLES = ("US06", "HWFET", "CHG-US06")  # CHG-<cycle> = the charge that follows that drive cycle
FIT = [("AM23NMC00103", t, c) for t in (25, 35) for c in FIT_CYCLES]
HOLDOUT_T = 45
CELLS = ("AM23NMC00103", "AM23NMC00104", "AM23NMC00105")
CYCLES = ("BCDC", "LA92", "HHDDT", "CSHVC", "FTP-72", "FTP-75", "HWFET", "IM", "US06", "PDTCB", "PDMHC", "OCTBC")
CHARGES = tuple(f"CHG-{c}" for c in CYCLES[:-1])  # the last cycle is followed by a partial storage charge
DOI = "10.14279/depositonce-25110"


def parquet(cell: str, temp_c: int) -> Path:
    dst = PARQUET / f"{cell}_std_{temp_c:02d}deg.parquet"
    if not dst.exists():  # extract one raw file from the archive (plain name, no path taken from the archive)
        PARQUET.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(DATA / "dataset.zip") as z, z.open(f"0_raw/{cell}/{dst.name}") as src:
            dst.write_bytes(src.read())
    return dst


def converted(cell: str, temp_c: int, cycle: str, folder: Path = VALIDATION) -> Path:
    if cycle.startswith("CHG-"):  # all charges of a file are cut at once, into CHARGE_DIR
        src, dst = (d / f"TUB_M50LT_{cell}_{cycle}_{temp_c}C.csv" for d in (CHARGE_DIR, folder))
        if not src.exists():
            CHARGE_DIR.mkdir(parents=True, exist_ok=True)
            convert_charges(parquet(cell, temp_c), cell, temp_c, CHARGE_DIR)
        if not dst.exists():
            shutil.copyfile(src, dst)
        return dst
    dst = folder / out_path(cell, temp_c, cycle).name
    if not dst.exists():
        folder.mkdir(parents=True, exist_ok=True)
        convert(find(PRE, cell, temp_c, cycle), dst)
    return dst


def discharged_ah(log: Log) -> float:
    return float(np.trapezoid(log.current_a, log.t_s) / 3600)


def summary(rows: list[dict]) -> dict:
    col = lambda k: np.array([r[k] for r in rows])  # noqa: E731
    return {"n": len(rows), "v_rmse_op_mv_median": round(float(np.median(col("v_rmse_op_mv"))), 1),
            "v_rmse_op_mv_max": round(float(col("v_rmse_op_mv").max()), 1),
            "v_rmse_mv_median": round(float(np.median(col("v_rmse_mv"))), 1),
            "v_rmse_mv_max": round(float(col("v_rmse_mv").max()), 1),
            "t_rmse_k_median": round(float(np.median(col("t_rmse_k"))), 2),
            "t_rmse_k_max": round(float(col("t_rmse_k").max()), 2),
            "t_rise_meas_k_mean": round(float(np.mean(col("t_rise_meas_k"))), 2),
            "t_rise_pred_k_mean": round(float(np.mean(col("t_rise_pred_k"))), 2),
            "core_minus_surface_max_k": round(float(col("core_minus_surface_max_k").max()), 2)}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    uncal_path = CELL_DIR / f"{CELL_ID}_uncalibrated.json"
    if not uncal_path.exists():  # first run: keep the pre-calibration generic cell for before/after comparison
        uncal_path.write_text((CELL_DIR / f"{CELL_ID}.json").read_text(encoding="utf-8"), encoding="utf-8")
    base = load_cell(f"{CELL_ID}_uncalibrated")

    fit_paths = [converted(*spec) for spec in FIT]
    fit_logs_ = [Log.read(p) for p in fit_paths]
    capacity = float(np.mean([discharged_ah(lg) for lg in fit_logs_ if not lg.name.split("_")[3].startswith("CHG")]))
    # SOC = 1 is the rested state after the CC-CV charge: pin the top OCV point to the voltage measured at the end of
    # the 2 h rest (otherwise it is barely constrained and drifts above the CV voltage)
    v_full = float(np.mean([lg.voltage_v[-1] for lg in fit_logs_ if lg.name.split("_")[3].startswith("CHG")]))
    top = len(base.ocv_v) - 1
    start = base.model_copy(update={"capacity_ah": round(capacity, 3), "ocv_v": base.ocv_v[:-1] + [round(v_full, 4)]})
    print(f"fitting {', '.join(p.name for p in fit_paths)} (capacity fixed at measured {capacity:.3f} Ah, "
          f"OCV(100 %) at measured rest voltage {v_full:.3f} V) ...")
    res = fit_logs(fit_logs_, start, free=("r_temp_k", "ocv", "c_th_j_k"), fixed=("capacity_ah", f"ocv_{top}"),
                   h_eff_guess=20.0)

    proxy = f"LG INR21700 M50LT proxy cell, TU Berlin Internal Temperature Dataset (DOI {DOI}, CC BY 4.0)"
    keep = [a for a in base.assumptions if a.id not in ("C-NMC-1", "C-NMC-2")]  # OCV and R are now fitted
    cal = res.cell.model_copy(update={
        "id": CELL_ID, "name": "Generic NMC 21700 5 Ah class (calibrated on LG M50LT proxy)",
        "r0_ohm": round(res.cell.r0_ohm, 5), "r1_ohm": round(res.cell.r1_ohm, 5), "tau_s": round(res.cell.tau_s, 1),
        "r_temp_k": round(res.cell.r_temp_k, 0),
        "sources": base.sources + [f"OCV, R0, R1, tau, r_temp_k fitted and capacity measured on {proxy}: US06, "
                                   f"HWFET and 1C CC-CV charge at 25 and 35 °C; hold-out at {HOLDOUT_T} °C — see "
                                   f"data/validation/{RECORD.name}"],
        "assumptions": keep + [Assumption(
            id="C-NMC-CAL", source=f"DOI {DOI}", affects=["cell", "electrical", "thermal"],
            text=f"OCV, R0, R1, tau, Arrhenius coefficient and capacity measured on a proxy cell (LG M50LT, drilled "
                 f"for an internal thermocouple) at 25–35 °C; hold-out checked at {HOLDOUT_T} °C. Not the cell that "
                 f"would be bought")],
    })
    (CELL_DIR / f"{CELL_ID}.json").write_text(json.dumps(cal.model_dump(), indent=2, ensure_ascii=False) + "\n",
                                              encoding="utf-8")

    def row(cell: str, cycle: str, f, log: Log) -> dict:
        return {"cell": cell, "cycle": cycle, "v_rmse_op_mv": round(f.v_rmse_op_mv, 1),
                "v_rmse_mv": round(f.v_rmse_mv, 1), "v_max_err_mv": round(f.v_max_err_mv, 0),
                "t_rmse_k": round(f.t_rmse_k, 2), "t_rise_meas_k": round(float(log.temp_c.max() - log.temp_c[0]), 2),
                "t_rise_pred_k": round(float(f.t_pred.max() - f.t_pred[0]), 2),
                "core_minus_surface_max_k": round(f.core_gap_k, 2)}

    held = {"drive": [c for c in CYCLES if c not in FIT_CYCLES], "charge": [c for c in CHARGES if c not in FIT_CYCLES]}
    print(f"hold-out at {HOLDOUT_T} °C: {len(CELLS)} cells x ({len(held['drive'])} drives + {len(held['charge'])} "
          f"charges) ...")
    rows: dict[str, list[dict]] = {"drive": [], "charge": []}
    for kind, cycles in held.items():
        for cell in CELLS:
            for cycle in cycles:
                log = Log.read(converted(cell, HOLDOUT_T, cycle, CHARGE_DIR if kind == "charge" else HOLDOUT_DIR))
                rows[kind].append(row(cell, cycle, evaluate(cal, res.h_eff, log, c_th=res.c_th), log))

    record = {
        "proxy": proxy, "fit_logs": [p.name for p in fit_paths], "capacity_ah_measured": round(capacity, 3), "ocv_full_v_measured": round(v_full, 4),
        "fitted": {k: round(v, 6) for k, v in res.fitted.items()},
        "chamber_h_eff_w_m2k": round(res.h_eff, 2), "rig_c_th_j_k": round(res.c_th, 1),
        "cell_c_th_j_k": round(cal.mass_kg * cal.cp_j_kgk, 1), "op_soc_min": OP_SOC_MIN,
        "fit": [row("AM23NMC00103", p.stem.split("_")[3], f, lg) | {"log": f.name}
                for p, f, lg in zip(fit_paths, res.fits, fit_logs_)],
        "holdout_temp_c": HOLDOUT_T,
        "holdout_summary": {kind: summary(r) for kind, r in rows.items()},
        "holdout": rows,
    }
    RECORD.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    print(f"\n{'param':<14}{'generic':>12}{'calibrated':>12}")
    for k in ("r0_ohm", "r1_ohm", "tau_s", "r_temp_k", "capacity_ah"):
        print(f"{k:<14}{getattr(base, k):>12.4g}{getattr(cal, k):>12.4g}")
    print("OCV  generic   ", " ".join(f"{x:.2f}" for x in base.ocv_v))
    print("OCV  calibrated", " ".join(f"{x:.2f}" for x in cal.ocv_v))
    print(f"test rig: h_eff {res.h_eff:.1f} W/m²K, heat capacity {res.c_th:.0f} J/K vs cell alone "
          f"{cal.mass_kg * cal.cp_j_kgk:.0f} J/K (neither used for packs)")
    for r in record["fit"]:
        print(f"fit  {r['log']}: V RMSE {r['v_rmse_op_mv']} mV (SOC >= 10 %), {r['v_rmse_mv']} mV (all) · "
              f"T RMSE {r['t_rmse_k']} K · rise {r['t_rise_meas_k']} meas / {r['t_rise_pred_k']} pred K")
    for kind, s in record["holdout_summary"].items():
        print(f"\nhold-out {kind}: {s}")


if __name__ == "__main__":
    main()
