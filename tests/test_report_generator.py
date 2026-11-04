"""VoltTwin Phase 6: report content/formatting and the scaled 1S-4P bench protocol."""

from __future__ import annotations

import re

import pytest

from src.config import REQUIREMENTS
from src.models.db import DatasheetDB
from src.pipeline import evaluate, robustness
from src.workbench.report_generator import BENCH_P, BENCH_S, bench_protocol, build_report, write_report


@pytest.fixture(scope="module")
def db():
    return DatasheetDB()


@pytest.fixture(scope="module")
def study(db):
    return evaluate(db.get_presets(), db)


@pytest.fixture(scope="module")
def report(db, study):
    return build_report(study, db, robustness(db.get_presets(), db))


def test_bench_protocol_hand_calc(db, study):
    d = study.by_id("option_b").run.design
    b = bench_protocol(d, db)
    assert (BENCH_S, BENCH_P) == (1, 4) and b.n_cells == 4
    assert b.v_nom_v == pytest.approx(3.65) and b.capacity_ah == pytest.approx(19.2)   # TASK.md: 3.65 V, 19.2 Ah
    assert b.ride_current_a == pytest.approx(0.5 * 4.8 * 4)
    assert b.charge_current_a == pytest.approx(d.charge_c_rate * 4.8 * 4)
    assert b.load_resistor_ohm == pytest.approx(3.65 / b.ride_current_a)
    assert b.fuse_a >= 1.5 * b.charge_current_a and b.fuse_a % 5 == 0
    assert [p.split(":")[0] for p in b.ntc_positions] == [f"T{k}" for k in range(1, 9)]
    assert 0 < b.expected_ride_dt_k < b.expected_peak_dt_k < 40


def test_bench_is_low_voltage_and_safe(db, study):
    b = bench_protocol(study.by_id("baseline").run.design, db)
    assert b.cv_limit_v <= 4.2 and b.ot_cutoff_c == 55.0
    text = " ".join(b.safety).lower()
    for must in ("1s", "fuse", "fireproof", "never unattended", "cutoff"):
        assert must in text, must


def test_report_contains_every_section_and_traceability_id(report):
    md = report.markdown
    for head in ("Recommendation", "Selected architecture", "Requirements compliance matrix", "Interface conflicts",
                 "Model assumptions and limitations", "Validation against measured data", "Traceability",
                 "1S-4P low-voltage bench test protocol"):
        assert f"## {head}" in md or head in md, head
    for req in REQUIREMENTS:
        assert req.id in md
    for rid in ("CF-TE-01", "CF-EM-01", "CF-PS-01", "A-EL-01", "A-TH-02"):
        assert rid in md
    assert "15 %" in md and "3D/CFD" in md and "Uniform contact" in md      # TASK.md-listed limitations
    assert "AIS-156" in md and "not validated" in md
    assert "provisional" in md                                              # robustness flip is stated


def test_markdown_tables_are_well_formed(report):
    lines = report.markdown.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("|---"):
            n = lines[i - 1].count("|")
            j = i + 1
            while j < len(lines) and lines[j].startswith("|"):
                assert lines[j].count("|") == n, lines[j]
                j += 1


def test_html_is_self_contained(report, tmp_path):
    h = report.html
    assert h.startswith("<!doctype html>") and "<title>" in h
    assert "plotly" in h.lower() and not re.search(r'<script[^>]+src="https?://', h)   # plotly.js inlined
    assert h.count("<ol>") >= 1 and h.count("<table") >= 10
    assert "<script>alert" not in h
    out = write_report(tmp_path / "r.html", report)
    assert out.read_text(encoding="utf-8") == h
    assert write_report(tmp_path / "r.md", report).read_text(encoding="utf-8") == report.markdown


def test_report_for_selected_design(db, study):
    rep = build_report(study, db, selected="baseline")
    assert "Selected architecture: Starting baseline" in rep.markdown
