"""VoltTwin Phase 2: coupled physics — hand calcs, energy balance, PCM, derating, convergence, PyBaMM, targets."""

from __future__ import annotations

import pytest

from src.config import BMS_CUTOFF_C
from src.models.db import DatasheetDB
from src.physics import simulate_design
from src.physics.electrical import BOL_R_MARGIN, pack_electrical
from src.physics.pybamm_runner import run_cell
from src.physics.targets import KNOWN_GAPS, compare_to_targets, status_mismatches
from src.physics.thermal import heat_capacity_j_k, simulate_cycle


@pytest.fixture(scope="module")
def db():
    return DatasheetDB()


@pytest.fixture(scope="module")
def runs(db):
    return {d.id: simulate_design(d, db) for d in db.get_presets()}


def preset(db, pid):
    return next(p for p in db.get_presets() if p.id == pid)


def test_electrical_hand_calc(db, runs):
    e = runs["baseline"].electrical
    assert e.v_nom_v == pytest.approx(13 * 3.65)
    assert e.capacity_ah == pytest.approx(12 * 4.8)
    assert e.nominal_energy_kwh == pytest.approx(156 * 3.65 * 4.8 / 1000)
    assert e.r_cell_ohm == pytest.approx(0.018 * (1 + BOL_R_MARGIN))
    assert e.r_cells_pack_ohm == pytest.approx(13 * 0.018 * 1.15 / 12)
    ni = db.get_busbar("ni_strip_015mm")
    assert e.r_busbar_ohm == pytest.approx(14 * 6.99e-8 * 0.022 / (0.15e-3 * 8e-3) / 12)
    assert ni.link_resistance_ohm > db.get_busbar("cu_busbar_015mm").link_resistance_ohm * 3


def test_charge_time_matches_c_rate_without_derating(runs):
    for pid, run in runs.items():
        assert run.result.charge_time_10_80_min == pytest.approx(0.7 / run.design.charge_c_rate * 60, abs=0.2), pid


@pytest.mark.parametrize("pid", ["baseline", "option_b"])
def test_energy_balance(db, runs, pid):
    """Σ(Q_gen − Q_rej)·dt equals the stored enthalpy: sensible heat + PCM latent heat."""
    run = runs[pid]
    tr, cell, cooling = run.nominal, db.get_cell(run.design.cell_id), db.get_cooling(run.design.cooling_id)
    c = heat_capacity_j_k(run.electrical, cell, cooling)
    e_lat = cooling.pcm_mass_kg * cooling.pcm_latent_j_kg
    h = lambda i: c * (tr.t_pack_c[i] - run.design.ambient_c) + tr.pcm_melt_fraction[i] * e_lat  # noqa: E731
    dt = tr.t_s[1] - tr.t_s[0]
    integral = ((tr.heat_gen_w[:-1] - tr.heat_reject_w[:-1]) * dt).sum()
    assert h(-1) - h(0) == pytest.approx(integral, rel=1e-6)


def test_pcm_buffers_peak(db):
    d = preset(db, "option_b")
    cell, busbar = db.get_cell(d.cell_id), db.get_busbar(d.busbar_id)
    pcm = db.get_cooling("al_fin_pcm")
    no_pcm = pcm.model_copy(update={"pcm_mass_kg": 0.0, "pcm_latent_j_kg": 0.0, "pcm_melt_c": None})
    pe = pack_electrical(d, cell, busbar)
    with_pcm = simulate_cycle(d, cell, pcm, pe, derate=False)
    without = simulate_cycle(d, cell, no_pcm, pe, derate=False)
    assert with_pcm.pcm_melt_fraction.max() > 0
    assert with_pcm.t_peak_c < without.t_peak_c - 1.0


def test_derating_caps_temperature_and_extends_charge(runs):
    for pid, run in runs.items():
        r = run.result
        assert r.t_peak_derated_c <= r.t_peak_c + 1e-9, pid
        assert r.charge_time_derated_min >= r.charge_time_10_80_min - 1e-9, pid
        assert r.charge_complete, pid
    base = runs["baseline"].result
    assert base.charge_time_derated_min > base.charge_time_10_80_min + 5      # baseline really derates
    assert base.t_peak_derated_c < BMS_CUTOFF_C                               # and stays under the cutoff
    assert runs["option_b"].result.charge_time_derated_min == runs["option_b"].result.charge_time_10_80_min


def test_time_step_convergence(db):
    d = preset(db, "baseline")
    cell, cooling, busbar = db.get_cell(d.cell_id), db.get_cooling(d.cooling_id), db.get_busbar(d.busbar_id)
    pe = pack_electrical(d, cell, busbar)
    a, b = (simulate_cycle(d, cell, cooling, pe, derate=True, dt=dt) for dt in (5.0, 1.0))
    assert a.t_peak_c == pytest.approx(b.t_peak_c, abs=0.1)
    assert a.charge_time_min == pytest.approx(b.charge_time_min, abs=0.5)


def test_copper_busbar_cuts_busbar_heat(db, runs):
    d = runs["baseline"].design.model_copy(update={"busbar_id": "cu_busbar_015mm"})
    cu = simulate_design(d, db).result
    assert cu.heat_busbar_w < runs["baseline"].result.heat_busbar_w / 3


def test_heat_breakdown_and_bom_sum(runs):
    for run in runs.values():
        r, m = run.result, run.mechanical
        assert r.heat_gen_w == pytest.approx(r.heat_cells_w + r.heat_reversible_w + r.heat_busbar_w)
        assert r.mass_kg == pytest.approx(sum(m.mass_breakdown_kg.values()))
        assert r.bom_cost_usd == pytest.approx(sum(m.cost_breakdown_usd.values()))
    assert runs["option_b"].result.heat_pcm_w > 0 and runs["baseline"].result.heat_pcm_w == 0


@pytest.mark.parametrize("pid", ["baseline", "option_a", "option_b"])
def test_requirement_verdicts_match_round1(db, runs, pid):
    assert status_mismatches(runs[pid].result, db.get_targets()[pid]) == {}


@pytest.mark.parametrize("pid", ["baseline", "option_a", "option_b"])
def test_values_within_tolerance_of_round1_except_known_gaps(db, runs, pid):
    for row in compare_to_targets(pid, runs[pid].result, db.get_targets()[pid]):
        if (pid, row.metric) in KNOWN_GAPS:
            assert not row.within, f"{pid}.{row.metric} now within tolerance — remove it from KNOWN_GAPS"
        else:
            assert row.within, f"{pid}.{row.metric}: simulated {row.simulated:.2f} vs target {row.target} ({row.tolerance})"


def test_pybamm_cross_check_both_chemistries(db):
    for pid in ("baseline", "option_a"):
        run = simulate_design(preset(db, pid), db, use_pybamm=True)
        assert run.result.engine == "pybamm", run.result.notes
        # SPMe reference-cell heat is lower than datasheet DCIR implies, but the same order of magnitude
        assert 0.3 < run.result.r_eff_ratio_vs_datasheet < 1.5
        assert run.electrochem.voltage_v[-1] > run.electrochem.voltage_v[0]  # charging raises voltage
    # the headline verdict does not depend on the engine
    assert simulate_design(preset(db, "baseline"), db, use_pybamm=True).result.requirement_status["REQ-TH-01"] == "FAIL"


def test_pybamm_failure_falls_back_to_surrogate(db):
    cell = db.get_cell("nmc21700_4p8ah").model_copy(update={"pybamm_parameter_set": "NoSuchSet"})
    ec = run_cell(cell, 1.0, 40.0, use_pybamm=True)
    assert ec.engine == "surrogate" and "PyBaMM unavailable" in ec.note
