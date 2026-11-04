"""VoltTwin Phase 5: workbench smoke test, figure rules, real-log validation replay, robustness sweep."""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from src.config import ROOT
from src.models.db import DatasheetDB
from src.physics.pybamm_runner import run_cell
from src.physics.replay import real_logs, replay_log
from src.pipeline import evaluate, robustness
from src.workbench import plots, views


@pytest.fixture(scope="module")
def db():
    return DatasheetDB()


@pytest.fixture(scope="module")
def study(db):
    return evaluate(db.get_presets(), db)


def test_only_real_logs_are_offered():
    names = [p.name for p in real_logs()]
    assert names and all(n.startswith("TUB_") for n in names)
    assert not any("SYNTHETIC" in n for n in names)


def test_replay_reports_honest_errors(db):
    cell = db.get_cell("nmc21700_4p8ah")
    rp = replay_log(next(p for p in real_logs() if "CHG" in p.name and "45C" in p.name), cell)
    assert 0 < rp.v_rmse_op_mv <= rp.v_rmse_mv + 1e-9
    # documented finding: the datasheet model under-predicts the measured temperature rise
    assert rp.t_rise_pred_k < rp.t_rise_meas_k
    with pytest.raises(ValueError, match="not validated"):
        replay_log(real_logs()[0], db.get_cell("lfp21700_3p8ah"))


def test_robustness_sweep_exposes_fragile_recommendation(db):
    rob = robustness(db.get_presets(), db)
    assert rob[1.0]["option_b"] == "OPTIMAL"
    assert rob[1.5]["option_b"] == "UNSAFE"      # flips at 1.5x heat — stated in the UI and report
    assert all(v["baseline"] == "UNSAFE" for v in rob.values())


def test_round1_comparison_off_when_heat_scaled(db):
    assert all(not ev.targets for ev in evaluate(db.get_presets(), db, heat_factor=1.5).designs)


def _no_dual_axes(fig):
    layout = fig.to_plotly_json()["layout"]
    return not any(k.startswith("yaxis") and v.get("overlaying") for k, v in layout.items())


def test_figures_build_without_dual_axes(db, study):
    colors = plots.design_colors(study)
    rp = replay_log(real_logs()[0], db.get_cell("nmc21700_4p8ah"))
    curves = {"NMC": run_cell(db.get_cell("nmc21700_4p8ah"), 1.0, 40.0)}
    figs = [plots.radar(study), plots.transient(study.designs[0], colors["baseline"]), plots.heat_breakdown(study),
            plots.validation_overlay(rp), plots.cell_curves(curves, {"NMC": colors["baseline"]})]
    for fig in figs:
        assert fig.data and _no_dual_axes(fig)
    assert len(set(colors.values())) == len(colors)          # one colour per design


def test_tables(study):
    assert len(views.requirement_grid(study)) == 7
    assert set(views.ranking_table(study)["Verdict"]) == {"OPTIMAL", "REJECTED", "UNSAFE"}
    gaps = views.target_gaps(study)
    assert (gaps["Within"] == "NO").sum() == 3 and gaps.loc[gaps["Within"] == "NO", "Explanation"].all()


def test_streamlit_app_runs_and_reacts():
    at = AppTest.from_file(str(ROOT / "src" / "workbench" / "app.py"), default_timeout=180).run()
    assert not at.exception
    assert len(at.tabs) == 4 and "Design option B" in at.success[0].value
    next(s for s in at.slider if s.label.startswith("Fast-charge")).set_value(1.4).run()
    assert not at.exception
    assert "Custom design" in at.markdown[0].value
