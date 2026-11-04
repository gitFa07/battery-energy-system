
import re

import numpy as np
import pytest

from packforge import load_study, rank, run_design
from packforge.loader import ROOT, build_design, deep_merge, load_design_dict
from packforge.schema import Scenario
from packforge.sim import build_pack, sensor_positions, simulate

STUDY = ROOT / "studies" / "escooter_48v"


@pytest.fixture(scope="module")
def study_and_results():
    study, designs = load_study(STUDY)
    return study, {d.id: run_design(d, study) for d in designs}


def variant(**overrides):
    return build_design(deep_merge(load_design_dict(STUDY / "baseline.json"), overrides))


def test_extends_merges_and_accumulates_assumptions():
    raw = load_design_dict(STUDY / "option_a_fastcharge.json")
    assert raw["topology"] == {"series": 13, "parallel": 10}  # inherited
    assert raw["cooling"]["type"] == "conduction_plate"  # overridden
    ids = [a["id"] for a in raw["assumptions"]]
    assert "A-01" in ids and "A-A1" in ids


def test_usable_energy_close_to_nominal(study_and_results):
    _, results = study_and_results
    for r in results.values():
        ratio = r.metrics["usable_energy_wh"] / r.metrics["energy_nominal_wh"]
        assert 0.9 < ratio < 1.06, (r.design.id, ratio)
        assert r.drive.end_reason[0] == "UV cutoff"


def test_charge_completes_on_cv(study_and_results):
    _, results = study_and_results
    for r in results.values():
        end = r.charge.end_step[0] - 1
        assert r.charge.end_reason[0] == "CV complete", r.design.id
        assert r.charge.v_cell_max[end, 0] == pytest.approx(r.design.control.cv_v_cell, abs=0.01)
        assert r.charge.soc_mean[end, 0] > 0.9  # 4.15 V CV stops the measured NMC OCV curve at ~92 %


def test_adiabatic_heat_balance():
    """With no cooling and no conduction, temperature rise must equal integrated heat / heat capacity."""
    d = variant(cooling={"h_eff_w_m2k": 0.0, "g_neighbor_w_k": 0.0}, control={"derate_start_c": 90, "derate_end_c": 95},
                protection={"ot_charge_c": 45})
    d = d.model_copy(update={"variation": d.variation.model_copy(update={"r0_sigma": 0.0, "capacity_sigma": 0.0})})
    tr = simulate(build_pack(d), Scenario(type="charge", start_soc=0.1, max_time_s=1200), 25.0)
    dt = tr.t_s[1] - tr.t_s[0]
    rise = tr.t_mean[-1, 0] - 25.0
    expected = np.nansum(tr.heat_w_mean[:-1, 0]) * dt / (d.cell.mass_kg * d.cell.cp_j_kgk)
    assert rise == pytest.approx(expected, rel=0.02)


def test_detects_cell_charge_limit_conflict(study_and_results):
    study, _ = study_and_results
    r = run_design(variant(control={"charge_c_rate": 1.2}), study)
    assert any(f.id == "IF-01" and f.severity == "fail" for f in r.findings)


def test_detects_protection_trip_when_derating_disabled(study_and_results):
    study, _ = study_and_results
    r = run_design(variant(control={"charge_c_rate": 0.95, "derate_start_c": 60, "derate_end_c": 70}), study)
    sev = {f.id: f.severity for f in r.findings}
    assert sev["IF-12"] == "warn" and sev["IF-14"] == "fail" and sev["REQ-03"] == "fail"
    assert r.charge.end_reason[0] == "OT trip (charge)"


def test_ranking_disqualifies_failing_design(study_and_results):
    study, results = study_and_results
    bad = run_design(variant(id="bad", control={"charge_c_rate": 1.2}), study)
    ranking = rank(list(results.values()) + [bad], study)
    assert not next(rk for rk in ranking if rk.design_id == "bad").eligible
    eligible = [rk.eligible for rk in ranking]
    assert eligible == sorted(eligible, reverse=True)  # every eligible design ranks above every disqualified one


def test_center_sensor_placement_hits_middle():
    rows, cols = sensor_positions(variant(sensing={"n_temp_sensors": 1, "placement": "center"}))
    assert (rows[0], cols[0]) in {(6, 4), (6, 5)}


def test_monte_carlo_batch_matches_single_run(study_and_results):
    study, results = study_and_results
    from packforge.engine import monte_carlo

    d = results["baseline"].design
    mc = monte_carlo(d, study, n=4, seed=d.variation.seed)
    assert mc["usable_energy_wh"][0] == pytest.approx(results["baseline"].metrics["usable_energy_wh"], rel=1e-9)


def cold_start(study):
    charge = study.scenarios["charge"].model_copy(update={"after": None})
    return study.model_copy(update={"scenarios": {**study.scenarios, "charge": charge}})


def test_chained_charge_starts_from_drive_end_state(study_and_results):
    study, results = study_and_results
    assert study.scenarios["charge"].after == "drive"
    r = results["baseline"]
    assert r.charge.t_max[0, 0] == pytest.approx(r.drive.final.temp[0].max())
    assert r.charge.soc_mean[0, 0] == pytest.approx(r.drive.final.soc[0].mean())


def test_hot_plug_in_exposes_sensor_blind_spot(study_and_results):
    """Edge NTCs cool first after a ride, so the baseline charges hot interior cells; Option C's observer does not."""
    study, results = study_and_results
    sev = lambda r: {f.id: f.severity for f in r.findings}["REQ-03"]  # noqa: E731
    assert sev(results["baseline"]) == "fail"
    assert sev(run_design(results["baseline"].design, cold_start(study))) == "pass"
    assert sev(results["option_c"]) == "pass"


@pytest.mark.parametrize("err", [-0.3, 0.3])
def test_observer_robust_to_cooling_model_error(study_and_results, err):
    study, results = study_and_results
    d = results["option_c"].design
    d = d.model_copy(update={"control": d.control.model_copy(update={"observer_h_error": err})})
    assert run_design(d, study).metrics["t_max_charge_c"] <= 45.0


@pytest.mark.parametrize("design_id", ["baseline", "option_a"])
def test_sim_agrees_with_hand_calc_thermal_bound(study_and_results, design_id):
    """The ideal profile (full current to the limit, then held there) is a floor; the BMS derates from below the
    limit on what its sensors see, so the sim may be slower by the derate-window margin but never much faster."""
    study, results = study_and_results
    m = run_design(results[design_id].design, cold_start(study)).metrics
    assert 0.95 <= m["charge_time_10_80_min"] / m["charge_time_bound_min"] <= 1.3


def test_fit_recovers_synthetic_parameters():
    """Method check: the synthetic log was generated with known 'true' parameters + sensor noise."""
    from packforge.fit import Log, fit
    from packforge.loader import load_cell

    log = Log.read(ROOT / "data" / "validation" / "SYNTHETIC_nmc21700_pulse.csv")
    res = fit(log, load_cell("nmc21700_5ah_uncalibrated"))  # the generic cell the log was generated from
    true = {"r0_ohm": 0.026, "r1_ohm": 0.009, "tau_s": 45.0, "capacity_ah": 4.85, "h_eff_w_m2k": 9.0}
    for k, v in true.items():
        assert res.fitted[k] == pytest.approx(v, rel=0.06), k
    assert res.v_rmse_mv < 4 and res.t_rmse_k < 0.25  # at the injected noise floor (3 mV, 0.15 K)


def test_report_contains_recommendation_and_traceability(study_and_results):
    from packforge.report import build_report

    study, results = study_and_results
    html = build_report(list(results.values()), study)
    assert "Recommended:" in html and "REQ-03" in html and "A-C2" in html and html.count("<table") >= 6


def test_ui_grid_and_verdict(study_and_results):
    from packforge import ui
    from packforge.engine import recommend
    from packforge.metrics import KPIS

    study, results = study_and_results
    rs = list(results.values())
    recs = recommend(rs, study)
    grid = ui.requirement_grid(rs, rank(rs, study), study, recs[0].design_id)
    n_checks = len(rs[0].findings)
    assert len(re.findall(r'class="c (?:pass|warn|fail)"', grid)) == n_checks * len(rs)
    assert grid.count('class="c fail"') == 1 and "disqualified" in grid  # baseline REQ-03 after a ride
    assert "Recommended: Option B" in ui.verdict(recs, rs)
    assert "No design meets" in ui.verdict([], rs)
    assert ui.kpi_table(rs, study).count("<tr>") == len(KPIS) + 1
    assert "Recommendation" in ui.verdict(recs, rs) and "Issues and fixes" in ui.verdict([], rs)


def test_ui_kpi_cards(study_and_results):
    from packforge import ui

    study, results = study_and_results
    base, best = results["baseline"], results["option_b"]
    cards = ui.kpi_cards(base, study)
    assert cards.count('class="card"') == len(ui.CARD_KPIS)
    assert cards.count('class="pill fail"') == 1 and "REQ-03" in cards  # baseline: hot plug-in breaks REQ-03
    assert 'class="c ' not in cards  # grid marks stay countable in test_ui_grid_and_verdict
    assert 'class="pill fail"' not in ui.kpi_cards(best, study)
    assert "ineligible" in ui.kpi_cards(base, study, eligible=False)
    assert "ineligible" not in cards
    # a KPI without a requirement gets no pill and no limit
    bare = study.model_copy(update={"requirements": [q for q in study.requirements if q.metric != "cost_inr"]})
    assert ui.kpi_cards(best, bare).count('class="pill ') == len(ui.CARD_KPIS) - 1


def test_ui_pill_always_has_words():
    from packforge import ui

    for sev, word in [("pass", "pass"), ("warn", "warning"), ("fail", "fail")]:
        assert ui.pill(sev) == f'<span class="pill {sev}">{word}</span>'
    assert ">ineligible<" in ui.pill("fail", "ineligible")


def test_ui_robustness_note(study_and_results):
    from packforge import ui
    from packforge.engine import Recommendation

    study, results = study_and_results
    rs = list(results.values())
    rec = lambda d: [Recommendation("recommended", d, "", "")]  # noqa: E731
    assert ui.robustness_note([], rs, 2.0) == ""
    assert ui.robustness_note(rec("option_b"), rs, 2.0, current=2.0) == ""  # slider already there
    ok = ui.robustness_note(rec("option_b"), rs, 2.0)
    assert "still passes" in ok and "pf-robust fail" not in ok
    bad = ui.robustness_note(rec("baseline"), rs, 2.0)  # baseline fails REQ-03 in these results
    assert "fails" in bad and "REQ-03" in bad and "pf-robust fail" in bad
    assert all("AIS" not in x for x in (ok, bad))


BANNED = ["delve", "foster", "leverage", "utilize", "facilitate", "empower", "streamline", "robust", "cutting-edge",
          "seamless", "game changer", "tapestry", "realm", "beacon", "multifaceted", "meticulous", "paramount",
          "transformative", "elevate", "embark", "supercharge", "harness", "ever-evolving", "it's worth noting"]


def test_ui_copy_has_no_banned_words(study_and_results):
    from packforge import ui
    from packforge.engine import recommend

    study, results = study_and_results
    rs = list(results.values())
    recs = recommend(rs, study)
    html = " ".join([ui.masthead(study, True, 1.5), ui.verdict(recs, rs), ui.verdict([], rs), ui.alternatives(recs),
                     ui.kpi_cards(rs[0], study, eligible=False), ui.robustness_note(recs, rs, 2.0),
                     ui.requirement_grid(rs, rank(rs, study), study, None)])
    text = (re.sub(r"<[^>]+>", " ", html) + (ROOT / "app.py").read_text(encoding="utf-8")).lower()  # visible text
    found = [w for w in BANNED if re.search(rf"\b{re.escape(w)}\b", text)]
    assert not found, found
    assert "ais-156" not in text and "ais 156" not in text


def test_figures_keep_transparent_background(study_and_results):
    from packforge import figures

    study, results = study_and_results
    rs = list(results.values())
    figs = [figures.radar(rs, study), figures.timeseries(rs, "charge", "Max cell temp °C"),
            figures.heatmap(rs[0], figures.heat_range(rs)), figures.histogram(np.linspace(1, 2, 30), "charge_time_min",
                                                                             figures.design_color(0)),
            figures.validation(np.arange(5.0), np.ones(5), np.ones(5), "V")]
    for f in figs:
        assert f.layout.paper_bgcolor == "rgba(0,0,0,0)" and f.layout.plot_bgcolor == "rgba(0,0,0,0)"
        assert f.layout.title.x == 0  # left-aligned titles
    assert [a.text for a in figs[3].layout.annotations] == ["P5", "P95"]


def test_app_renders():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=300).run()
    assert not at.exception
    assert [t.label for t in at.tabs] == ["Compare", "Behaviour", "Issues and fixes", "Evidence",
                                          "Validation and spread"]


def test_charge_time_includes_thermal_hold(study_and_results):
    study, results = study_and_results
    for r in results.values():
        m = r.metrics
        assert m["thermal_hold_min"] >= 0
        assert m["charge_time_min"] >= m["thermal_hold_min"] + m["charge_time_10_80_min"] - 1e-9
    cold = run_design(results["baseline"].design, cold_start(study)).metrics
    assert cold["thermal_hold_min"] == 0


def test_recommend_gives_best_alternative_and_firmware_retrofit(study_and_results):
    from packforge.engine import HARDWARE_EXCLUDE, recommend

    study, results = study_and_results
    rs = list(results.values())
    recs = {r.role: r for r in recommend(rs, study)}
    ranking = rank(rs, study)
    assert recs["recommended"].design_id == ranking[0].design_id and ranking[0].eligible
    best = results[recs["recommended"].design_id]
    missed = [f.requirement for f in best.warns if f.requirement]
    if "if_limits" in recs:  # the alternative passes every should-requirement the recommended design misses
        alt = {f.requirement: f.severity for f in results[recs["if_limits"].design_id].findings if f.requirement}
        assert missed and all(alt[q] == "pass" for q in missed)
    retro = results[recs["retrofit"].design_id]  # Option C: same hardware as the baseline, firmware only
    assert retro.design.model_dump(exclude=HARDWARE_EXCLUDE) == rs[0].design.model_dump(exclude=HARDWARE_EXCLUDE)
    assert retro.metrics["cost_inr"] == rs[0].metrics["cost_inr"] and not retro.fails


def test_log_replay_starts_hot_and_relaxes_to_ambient():
    """A log with ambient_c below its first temperature cools towards ambient when no current flows."""
    from packforge.fit import Log, predict
    from packforge.loader import load_cell

    t = np.arange(0, 3601, 1.0)
    log = Log(t, np.zeros_like(t), np.full_like(t, 3.7), np.full_like(t, 30.0), soc=np.full_like(t, 0.5),
              ambient_c=25.0)
    _, temp = predict(load_cell("nmc21700_5ah"), np.array([[20.0]]), log, names=["h_eff_w_m2k"])
    assert temp[0, 0] == pytest.approx(30.0, abs=0.01) and 25.0 < temp[0, -1] < 27.0


@pytest.mark.parametrize("log_name, v_max_mv, t_max_k", [
    ("TUB_M50LT_AM23NMC00104_CHG-FTP-75_45C.csv", 25, 0.8),  # 1C charge, another cell, 45 °C
    ("TUB_M50LT_AM23NMC00103_BCDC_45C.csv", 30, 0.4),  # drive cycle not in the fit, 45 °C
])
def test_calibrated_cell_predicts_holdout_logs(log_name, v_max_mv, t_max_k):
    """Hold-out guard: measured proxy-cell logs never used in the fit (other cycle, cell and temperature)."""
    from packforge.fit import VALIDATION_DIR, Log, evaluate, load_calibration
    from packforge.loader import load_cell

    cal = load_calibration("nmc21700_5ah")
    assert log_name not in cal["fit_logs"] and all("_45C" not in f for f in cal["fit_logs"])
    f = evaluate(load_cell("nmc21700_5ah"), cal["chamber_h_eff_w_m2k"], Log.read(VALIDATION_DIR / log_name),
                 c_th=cal["rig_c_th_j_k"])
    assert f.v_rmse_op_mv < v_max_mv and f.t_rmse_k < t_max_k


def test_extra_heat_only_makes_designs_hotter(study_and_results):
    from packforge.engine import with_heat_factor

    study, results = study_and_results
    r = results["option_a"]
    hot = run_design(with_heat_factor(r.design, 2.0), study)
    assert hot.metrics["t_max_drive_c"] > r.metrics["t_max_drive_c"]
    assert hot.metrics["charge_time_min"] > r.metrics["charge_time_min"]
