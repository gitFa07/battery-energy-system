"""One call from design inputs to a ranked, traced study: simulate → conflicts → rank → traceability →
Round-1 comparison. The API, workbench, report and demo all use this, so they never disagree."""

from __future__ import annotations

from dataclasses import dataclass

from src.models.db import DatasheetDB
from src.models.schemas import ModuleDesignInput, TraceabilityRecord
from src.physics import SimulationRun, simulate_design
from src.physics.targets import TargetComparison, compare_to_targets
from src.validator import ConflictAlert, Ranked, build_traceability, detect_conflicts, recommend


@dataclass
class DesignEvaluation:
    run: SimulationRun
    alerts: list[ConflictAlert]
    traceability: list[TraceabilityRecord]
    ranked: Ranked
    targets: list[TargetComparison]      # empty unless the design id has Round-1 targets

    @property
    def id(self) -> str:
        return self.run.design.id


@dataclass
class StudyEvaluation:
    designs: list[DesignEvaluation]      # input order
    ranking: list[Ranked]                # best first

    def by_id(self, design_id: str) -> DesignEvaluation:
        return next(d for d in self.designs if d.id == design_id)

    @property
    def recommended(self) -> DesignEvaluation | None:
        top = self.ranking[0] if self.ranking else None
        return self.by_id(top.design_id) if top and top.verdict == "OPTIMAL" else None


def evaluate(designs: list[ModuleDesignInput], db: DatasheetDB, use_pybamm: bool = False) -> StudyEvaluation:
    ids = [d.id for d in designs]
    if len(set(ids)) != len(ids):
        raise ValueError(f"design ids must be unique: {ids}")
    runs = [simulate_design(d, db, use_pybamm) for d in designs]
    alerts = {r.design.id: detect_conflicts(r, db) for r in runs}
    ranking = recommend(runs, alerts)
    ranked = {rk.design_id: rk for rk in ranking}
    targets = db.get_targets()
    presets = {p.id: p for p in db.get_presets()}
    # Round-1 targets apply only to the unmodified preset, not to an edited design that kept its id
    evals = [DesignEvaluation(r, alerts[r.design.id], build_traceability(r), ranked[r.design.id],
                              compare_to_targets(r.design.id, r.result, targets[r.design.id])
                              if r.design.id in targets and presets.get(r.design.id) == r.design else [])
             for r in runs]
    return StudyEvaluation(evals, ranking)
