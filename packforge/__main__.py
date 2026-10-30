"""CLI: python -m packforge [study_dir] [--mc N] [--report out.html] [--stress 2.0]

Prints the KPI comparison, conflicts with fixes, and the recommendation; optionally writes the HTML report.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from .engine import monte_carlo, rank, recommend, run_design, with_heat_factor
from .loader import ROOT, load_study
from .metrics import KPIS, METRICS, fmt


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="packforge")
    ap.add_argument("study", nargs="?", default=str(ROOT / "studies" / "escooter_48v"))
    ap.add_argument("--mc", type=int, default=0, help="Monte Carlo samples per design (cell variation)")
    ap.add_argument("--report", type=Path, help="write a self-contained HTML design report")
    ap.add_argument("--stress", type=float, default=2.0, help="unmodelled-heat factor for the robustness re-run (1 = off)")
    args = ap.parse_args()

    study, designs = load_study(Path(args.study))
    results = [run_design(d, study) for d in designs]
    print(f"\n{study.application}\n")

    w = 34
    print("KPI".ljust(w) + "".join(r.design.id.rjust(16) for r in results))
    for k in KPIS:
        print(METRICS[k].label.ljust(w) + "".join(fmt(k, r.metrics[k]).rjust(16) for r in results))

    for r in results:
        print(f"\n== {r.design.name}: {len(r.fails)} fail, {len(r.warns)} warn")
        for f in r.fails + r.warns:
            print(f"  [{f.severity.upper()}] {f.id} {f.title}: {f.detail}")
            if f.fixes:
                print(f"      fixes: {'; '.join(f.fixes)}")

    print("\n== Ranking")
    for i, rk in enumerate(rank(results, study), 1):
        flag = "" if rk.eligible else "  (disqualified: " + ", ".join(rk.reasons) + ")"
        print(f"  {i}. {rk.design_id:<12} score {rk.score:5.1f}{flag}")
    for rec in recommend(results, study):
        print(f"  → {rec.headline} — {rec.why}")

    stress = None
    if args.stress != 1:
        stress = [run_design(with_heat_factor(d, args.stress), study) for d in designs]
        print(f"\n== Robustness: cells generate {args.stress:g}x the modelled heat")
        for a, b in zip(results, stress):
            print(f"  {a.design.id:<12} charge {fmt('charge_time_min', b.metrics['charge_time_min']):>10}  "
                  f"fails: {', '.join(f.id for f in b.fails) or 'none'}")
        for rec in recommend(stress, study):
            print(f"  → {rec.headline}")

    if args.report:
        from .report import build_report

        args.report.write_text(build_report(results, study, stress), encoding="utf-8")
        print(f"\nreport written to {args.report}")

    if args.mc:
        print(f"\n== Monte Carlo cell variation ({args.mc} packs per design): mean ± std  [P5 – P95]")
        for d in designs:
            mc = monte_carlo(d, study, n=args.mc)
            for k in ("usable_energy_wh", "t_max_charge_c", "delta_t_c"):
                v = mc[k]
                print(f"  {d.id:<12} {METRICS[k].label:<26} {v.mean():8.1f} ± {v.std():5.1f}"
                      f"  [{np.percentile(v, 5):.1f} – {np.percentile(v, 95):.1f}]")


if __name__ == "__main__":
    main()
