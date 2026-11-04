"""VoltTwin Phase 3: conflict rules, radar margins, TOPSIS ranking/verdicts, traceability integrity."""

from __future__ import annotations

import numpy as np
import pytest

from src.models.db import DatasheetDB
from src.physics import simulate_design
from src.physics.assumptions import ASSUMPTIONS
from src.validator import build_traceability, detect_conflicts, recommend
from src.validator.topsis_recommender import RADAR_AXES, margin_score, topsis


@pytest.fixture(scope="module")
def db():
    return DatasheetDB()


@pytest.fixture(scope="module")
def runs(db):
    return {d.id: simulate_design(d, db) for d in db.get_presets()}


def fired(run, db, severity=None):
    return {a.rule_id for a in detect_conflicts(run, db)
            if a.severity != "PASS" and (severity is None or a.severity == severity)}


def variant(db, pid, **update):
    d = next(p for p in db.get_presets() if p.id == pid).model_copy(update=update)
    return simulate_design(d, db)


def test_verdicts_match_round1(db, runs):
    ranked = recommend(list(runs.values()), {k: detect_conflicts(r, db) for k, r in runs.items()})
    targets = db.get_targets()
    assert {rk.design_id: rk.verdict for rk in ranked} == {k: t["verdict"] for k, t in targets.items()}
    assert ranked[0].design_id == "option_b"
    assert runs["option_b"].result.verdict == "OPTIMAL"


def test_rule1_thermal_electrical(db, runs):
    assert {"CF-TE-01", "CF-TE-03"} <= fired(runs["baseline"], db, "CRITICAL")
    assert "CF-TE-02" in fired(runs["option_b"], db, "WARNING")   # relies on PCM, flagged but not disqualifying
    assert "CF-TE-01" not in fired(runs["option_a"], db)


def test_rule2_electro_mechanical(db, runs):
    assert {"CF-EM-01", "CF-EM-02"} <= fired(runs["option_a"], db, "CRITICAL")
    assert not fired(runs["option_b"], db) & {"CF-EM-01", "CF-EM-02"}


def test_rule3_protection_and_sensing(db, runs):
    assert {"CF-PS-01", "CF-PS-02"} <= fired(runs["baseline"], db, "CRITICAL")   # 115 A peak vs 100 A
    assert "CF-PS-04" in fired(runs["baseline"], db, "WARNING")                    # 4 NTCs on NMC
    assert "CF-PS-03" in fired(runs["baseline"], db, "WARNING")                    # Ni strip ampacity
    assert not fired(runs["option_b"], db) & {"CF-PS-01", "CF-PS-02", "CF-PS-04"}


def test_fixing_protection_clears_rule3(db):
    fixed = variant(db, "baseline", fuse_id="pyro_fuse_120a", bms_id="bms_active", n_ntc=6,
                    busbar_id="cu_busbar_015mm")
    assert not fired(fixed, db) & {"CF-PS-01", "CF-PS-02", "CF-PS-03", "CF-PS-04"}


def test_overcharge_and_sensor_overflow_flagged(db):
    fast = variant(db, "option_b", charge_c_rate=2.0)
    alerts = {a.rule_id: a for a in detect_conflicts(fast, db)}
    assert alerts["CF-PS-06"].severity == "CRITICAL" and alerts["CF-PS-06"].safety
    ranked = recommend([fast], {fast.design.id: list(alerts.values())})
    assert ranked[0].verdict == "UNSAFE"
    assert "CF-PS-05" in fired(variant(db, "option_b", n_ntc=10), db, "CRITICAL")


def test_alerts_carry_fixes_only_when_violated(db, runs):
    for run in runs.values():
        for a in detect_conflicts(run, db):
            assert bool(a.fixes) == (a.severity != "PASS"), a.rule_id
            assert a.detail and a.subsystems


def test_margin_score_scale():
    assert margin_score("REQ-ME-01", 18.0, 40) == pytest.approx(50)      # at the limit
    assert margin_score("REQ-ME-01", 9.0, 40) == pytest.approx(75)
    assert margin_score("REQ-ME-01", 40.0, 40) == 0                       # clipped
    assert margin_score("REQ-TH-01", 40.0, 40) == pytest.approx(100)      # temperature span = limit − ambient
    assert margin_score("REQ-TH-01", 45.0, 40) == pytest.approx(75)
    assert margin_score("REQ-EL-02", 2.40, 40) == pytest.approx(50)       # ≥ requirement


def test_radar_has_six_axes_in_range(runs):
    from src.validator import radar_margins
    for run in runs.values():
        m = radar_margins(run)
        assert list(m) == list(RADAR_AXES) and all(0 <= v <= 100 for v in m.values())


def test_topsis_hand_example():
    m = np.array([[1.0, 10.0], [2.0, 5.0], [1.5, 7.5]])        # criterion 0 benefit, 1 cost
    c = topsis(m, np.array([0.5, 0.5]), np.array([True, False]))
    assert c[1] == pytest.approx(1.0) and c[0] == pytest.approx(0.0)  # design 1 dominates, design 0 is dominated
    assert 0 < c[2] < 1


def test_traceability_chain_integrity(db, runs):
    tables = {"cells": db.get_cell, "cooling": db.get_cooling, "busbars": db.get_busbar,
              "protection": db.get_protection}
    for run in runs.values():
        records = build_traceability(run)
        assert len(records) == 7
        for rec in records:
            assert rec.value == pytest.approx(getattr(run.result, rec.simulated_metric))
            assert rec.status == run.result.requirement_status[rec.requirement_id]
            assert set(rec.assumptions) <= set(ASSUMPTIONS)
            for ref in rec.datasheet_parameters:
                owner, field = ref.split(".", 1)
                if owner == run.design.id:
                    assert hasattr(run.design, field), ref
                    continue
                spec = None
                for get in tables.values():
                    try:
                        spec = get(owner)
                        break
                    except KeyError:
                        pass
                assert spec is not None and hasattr(spec, field), ref
