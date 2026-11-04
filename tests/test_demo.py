"""VoltTwin Phase 7: the CLI demo runs end to end and its verdicts match Round-1 (exit code 0)."""

from __future__ import annotations

from run_demo import main


def test_cli_demo(tmp_path, capsys):
    report = tmp_path / "demo_report.md"
    assert main(["--cli-only", "--db", str(tmp_path / "demo.db"), "--report", str(report)]) == 0
    out = capsys.readouterr().out
    for section in ("Seed datasheet repository", "Verify against Round-1", "Ranking and conflicts", "Robustness",
                    "Recommendation"):
        assert section in out
    assert "UNEXPLAINED" not in out                       # every Round-1 gap has a stated reason
    assert report.exists() and "## Recommendation" in report.read_text(encoding="utf-8")
