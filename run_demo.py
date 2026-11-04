"""VoltTwin Studio demo runner: seed SQLite → simulate the three presets → verify against Round-1 targets →
print comparison, conflicts and robustness → write the report → (optionally) launch the API and the workbench.

    .venv/Scripts/python run_demo.py --cli-only                 # terminal demo, exits 0 if verdicts match Round-1
    .venv/Scripts/python run_demo.py                            # + FastAPI on :8000 and Streamlit on :8501
    .venv/Scripts/python run_demo.py --cli-only --pybamm --report volttwin_report.html
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from src.config import DATASHEET_DIR, REQUIREMENTS, ROOT
from src.models.db import DatasheetDB
from src.physics.targets import status_mismatches
from src.pipeline import evaluate, robustness
from src.workbench.report_generator import bench_protocol, build_report, write_report

ICON = {"CRITICAL": "✗", "WARNING": "!", "PASS": "✓"}


def rule(title: str) -> None:
    print(f"\n── {title} " + "─" * max(0, 100 - len(title)))


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cli-only", action="store_true", help="do not launch the API and workbench")
    ap.add_argument("--pybamm", action="store_true", help="cell heat from PyBaMM SPMe instead of datasheet R0")
    ap.add_argument("--db", type=Path, default=DATASHEET_DIR / "volttwin.db", help="SQLite file to (re)seed")
    ap.add_argument("--report", type=Path, help="write the design report (.html or .md)")
    ap.add_argument("--api-port", type=int, default=8000)
    ap.add_argument("--ui-port", type=int, default=8501)
    args = ap.parse_args(argv)

    rule("1  Seed datasheet repository")
    db = DatasheetDB(args.db)
    print(f"{args.db}: {len(db.list_cells())} cells, {len(db.list_cooling())} cooling, {len(db.list_busbars())} "
          f"interconnects, {len(db.list_protection())} protection parts, {len(db.get_presets())} presets")

    rule("2  Simulate presets (ride at 40 °C, then fast charge 10 → 80 %)")
    t0 = time.perf_counter()
    study = evaluate(db.get_presets(), db, use_pybamm=args.pybamm)
    print(f"engine: {study.designs[0].run.result.engine} · {time.perf_counter() - t0:.1f} s")
    names = [ev.run.design.name.split(" (")[0] for ev in study.designs]
    print(f"{'Requirement':<44}" + "".join(f"{n:>20}" for n in names))
    for req in REQUIREMENTS:
        cells = [f"{getattr(ev.run.result, req.metric):.2f} {ev.run.result.requirement_status[req.id]}"
                 for ev in study.designs]
        print(f"{req.id + ' ' + req.text[:30]:<44}" + "".join(f"{c:>20}" for c in cells))

    rule("3  Verify against Round-1 targets (±10 %, ±3 K)")
    targets = db.get_targets()
    mismatched = False
    for ev in study.designs:
        mm = status_mismatches(ev.run.result, targets[ev.id])
        verdict_ok = ev.ranked.verdict == targets[ev.id]["verdict"]
        mismatched |= bool(mm) or not verdict_ok
        within = sum(t.within for t in ev.targets)
        print(f"{ev.run.design.name:<40} verdict {ev.ranked.verdict:<9} (Round-1 {targets[ev.id]['verdict']}) "
              f"{'✓' if verdict_ok and not mm else '✗ ' + str(mm)} · values within tolerance {within}/{len(ev.targets)}")
        for t in ev.targets:
            if not t.within:
                print(f"    gap {t.metric}: {t.simulated:.1f} vs {t.target:g} — {t.known_gap or 'UNEXPLAINED'}")

    rule("4  Ranking and conflicts")
    for i, rk in enumerate(study.ranking, 1):
        print(f"{i}. {rk.name:<40} {rk.verdict:<10} TOPSIS {rk.closeness:.3f}")
    for ev in study.designs:
        active = [a for a in ev.alerts if a.severity != "PASS"]
        print(f"\n{ev.run.design.name}: {len(active)} conflict(s)")
        for a in active:
            print(f"  {ICON[a.severity]} {a.severity:<8}{' safety' if a.safety else '':<7} {a.rule_id} {a.title}: "
                  f"{a.detail}")

    rule("5  Robustness: verdicts if real cells make more heat than the datasheet model")
    rob = robustness(db.get_presets(), db)
    for f, verdicts in rob.items():
        print(f"heat × {f:<4g}" + "".join(f"{v:>20}" for v in verdicts.values()))
    print("Real-log replays (TU Berlin LG M50LT, CC BY 4.0) show the datasheet model under-predicts the temperature "
          "rise 2-4x;\nthe 1S-4P bench test measures that factor for these cells.")

    rec = study.recommended
    rule("6  Recommendation")
    if rec:
        b = bench_protocol(rec.run.design, db)
        print(f"{rec.run.design.name} — provisional until the bench heat factor is measured.")
        print(f"Bench: 1S-{b.n_cells}P, {b.v_nom_v:.2f} V, {b.capacity_ah:.1f} Ah, charge {b.charge_current_a:.1f} A, "
              f"fuse {b.fuse_a:g} A, expected peak ΔT {b.expected_peak_dt_k:.1f} K at {b.ambient_c:g} °C lab ambient.")
    else:
        print("No design meets every requirement without a critical conflict.")
    if args.report:
        path = write_report(args.report, build_report(study, db, rob))
        print(f"report → {path}")
    db.close()

    if args.cli_only:
        return 1 if mismatched else 0

    rule("7  Launch services (Ctrl+C to stop)")
    py = sys.executable
    procs = [subprocess.Popen([py, "-m", "uvicorn", "src.api.main:app", "--port", str(args.api_port)], cwd=ROOT),
             subprocess.Popen([py, "-m", "streamlit", "run", "src/workbench/app.py", "--server.port",
                               str(args.ui_port), "--server.headless", "true"], cwd=ROOT)]
    print(f"API docs   http://localhost:{args.api_port}/docs\nWorkbench  http://localhost:{args.ui_port}")
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()
    return 1 if mismatched else 0


if __name__ == "__main__":
    raise SystemExit(main())
