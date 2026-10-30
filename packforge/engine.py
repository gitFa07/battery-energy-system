"""Run designs through the model chain, compare them and recommend one."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .checks import Finding, run_checks
from .metrics import METRICS, all_metrics
from .schema import Design, Study
from .sim import Pack, Trace, build_pack, simulate


@dataclass
class DesignResult:
    design: Design
    metrics: dict[str, float]
    findings: list[Finding]
    charge: Trace
    drive: Trace

    @property
    def fails(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "fail"]

    @property
    def warns(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warn"]


def run_scenarios(pack: Pack, study: Study, dt: float) -> tuple[Trace, Trace]:
    """Simulate every scenario, honouring `after` chains; return the (charge, drive) traces."""
    traces: dict[str, Trace] = {}

    def run(name: str, seen: tuple[str, ...] = ()) -> Trace:
        if name in seen:
            raise ValueError(f"scenario chain loops: {' -> '.join(seen + (name,))}")
        if name not in traces:
            sc = study.scenarios[name]
            init = run(sc.after, seen + (name,)).final if sc.after else None
            traces[name] = simulate(pack, sc, study.ambient_c, name, dt, init)
        return traces[name]

    for name in study.scenarios:
        run(name)
    pick = lambda kind: traces[next(n for n, sc in study.scenarios.items() if sc.type == kind)]  # noqa: E731
    return pick("charge"), pick("drive")


def with_heat_factor(design: Design, factor: float) -> Design:
    """Same design with its cells generating `factor` x the modelled heat (the BMS observer is not told)."""
    return design.model_copy(update={"cell": design.cell.model_copy(update={"heat_factor": factor})})


def run_design(design: Design, study: Study, dt: float = 2.0) -> DesignResult:
    charge, drive = run_scenarios(build_pack(design), study, dt)
    m = all_metrics(design, charge, drive, study.ambient_c)
    return DesignResult(design, m, run_checks(design, study, m, charge.events[0]), charge, drive)


def monte_carlo(design: Design, study: Study, n: int = 50, seed: int = 1, dt: float = 2.0) -> dict[str, np.ndarray]:
    """Sample cell-to-cell variation across `n` packs in one vectorised run."""
    charge, drive = run_scenarios(build_pack(design, n_samples=n, seed=seed), study, dt)
    rows = [all_metrics(design, charge, drive, study.ambient_c, i) for i in range(n)]
    return {k: np.array([r[k] for r in rows]) for k in rows[0]}


@dataclass
class Ranking:
    design_id: str
    score: float
    eligible: bool
    reasons: list[str]


def rank(results: list[DesignResult], study: Study) -> list[Ranking]:
    """Weighted, min-max normalised score. Any failed must-requirement or interface rule disqualifies."""
    out = []
    for r in results:
        score = 0.0
        for metric, w in study.score_weights.items():
            vals = [x.metrics[metric] for x in results if not math.isnan(x.metrics[metric])]
            v = r.metrics[metric]
            if math.isnan(v) or not vals:
                continue
            lo, hi = min(vals), max(vals)
            norm = 0.5 if hi == lo else (v - lo) / (hi - lo)
            score += abs(w) * (norm if w > 0 else 1 - norm)
        total = sum(abs(w) for w in study.score_weights.values()) or 1
        reasons = [f"{f.id}: {f.title}" for f in r.fails]
        out.append(Ranking(r.design.id, 100 * score / total, not r.fails, reasons))
    return sorted(out, key=lambda x: (x.eligible, x.score), reverse=True)


@dataclass
class Recommendation:
    role: str  # "recommended" | "if_limits" | "retrofit"
    design_id: str
    headline: str
    why: str


HARDWARE_EXCLUDE = {"id", "name", "description", "control", "assumptions"}  # everything else is hardware


def recommend(results: list[DesignResult], study: Study) -> list[Recommendation]:
    """Up to three answers: the best eligible design; the best eligible design that meets the should-requirements
    the recommended one misses; and the best eligible design that keeps the baseline's (first design's) hardware
    and changes only BMS settings — a firmware update for packs already built."""
    ranking = rank(results, study)
    by_id = {r.design.id: r for r in results}
    eligible = [by_id[rk.design_id] for rk in ranking if rk.eligible]
    if not eligible:
        return []
    best, out = eligible[0], []
    missed = [f.requirement for f in best.warns if f.requirement]
    out.append(Recommendation("recommended", best.design.id, f"Recommended: {best.design.name}",
                              "best score among designs that meet every must-requirement and interface rule"
                              + (f"; misses {', '.join(missed)}" if missed else "")))

    sev = lambda r, q: next(f.severity for f in r.findings if f.requirement == q)  # noqa: E731
    alt = next((r for r in eligible[1:] if missed and all(sev(r, q) == "pass" for q in missed)), None)
    if alt:
        texts = " and ".join(q.text.lower() for q in study.requirements if q.id in missed)
        out.append(Recommendation("if_limits", alt.design.id, f"If {texts} are hard limits: {alt.design.name}",
                                  f"meets {', '.join(missed)}; open: "
                                  + (", ".join(f.requirement or f.id for f in alt.warns) or "nothing flagged")))

    base = results[0]
    hw = lambda d: d.model_dump(exclude=HARDWARE_EXCLUDE)  # noqa: E731
    retro = next((r for r in eligible if r is not base and hw(r.design) == hw(base.design)), None)
    if retro:
        delta = retro.metrics["cost_inr"] - base.metrics["cost_inr"]
        out.append(Recommendation("retrofit", retro.design.id, f"Retrofit for packs already built: "
                                  f"{retro.design.name}", f"same hardware as {base.design.name}, only BMS settings "
                                  f"change (₹{delta:,.0f} per pack); charge time {retro.metrics['charge_time_min']:.0f} min "
                                  f"vs {base.metrics['charge_time_min']:.0f} min"
                                  + (f"; fixes {', '.join(f.id for f in base.fails)}" if base.fails else "")))
    return out


def traceability(result: DesignResult, study: Study) -> list[dict[str, str]]:
    """Requirement → metric → value → status → evidence → model → assumptions it rests on."""
    by_id = {f.id: f for f in result.findings}
    rows = []
    for req in study.requirements:
        meta = METRICS.get(req.metric)
        subs = set(meta.subsystems) if meta else set()
        assumptions = [a.id for a in result.design.all_assumptions() if subs & set(a.affects)]
        f = by_id[req.id]
        rows.append({
            "requirement": req.id, "text": req.text, "metric": req.metric, "result": f.detail.split(" — ")[0],
            "status": f.severity, "evidence": meta.evidence if meta else "", "model": meta.model if meta else "",
            "subsystems": ", ".join(sorted(subs)), "assumptions": ", ".join(assumptions),
        })
    return rows
