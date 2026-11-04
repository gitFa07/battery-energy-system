"""VoltTwin Phase 4: REST endpoints — status codes, validation, payload fidelity vs the pipeline."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.main import app, get_db
from src.pipeline import evaluate


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def presets():
    return [p.model_dump() for p in get_db().get_presets()]


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["engines"]["surrogate"] is True
    assert body["datasheets"] == {"cells": 2, "cooling": 3, "busbars": 2, "protection": 6, "presets": 3}


def test_datasheets(client):
    body = client.get("/api/v1/datasheets").json()
    assert {c["id"] for c in body["cells"]} == {"nmc21700_4p8ah", "lfp21700_3p8ah"}
    assert len(body["requirements"]) == 7 and "A-EL-01" in body["assumptions"]
    assert body["limits"]["bms_cutoff_c"] == 55.0


def test_simulate_matches_pipeline(client, presets):
    r = client.post("/api/v1/simulate", json={"design": presets[0], "include_timeseries": True,
                                               "timeseries_points": 50})
    assert r.status_code == 200
    body = r.json()
    ev = evaluate([get_db().get_presets()[0]], get_db()).designs[0]
    assert body["result"]["t_peak_c"] == pytest.approx(ev.run.result.t_peak_c)
    assert body["result"]["requirement_status"]["REQ-TH-01"] == "FAIL"
    assert body["verdict"] == "UNSAFE"
    assert {c["rule_id"] for c in body["conflicts"]} >= {"CF-TE-01", "CF-PS-01"}
    assert len(body["traceability"]) == 7 and body["round1_comparison"]
    ts = body["timeseries"]["nominal"]
    assert len(ts["t_s"]) <= 50 and set(ts["phase"]) == {"ride", "charge"}


def test_compare_presets_default(client):
    r = client.post("/api/v1/compare", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["recommended"] == "option_b"
    assert {x["design_id"]: x["verdict"] for x in body["ranking"]} == {
        "option_b": "OPTIMAL", "option_a": "REJECTED", "baseline": "UNSAFE"}
    assert set(body["radar"]["option_b"]) == {"Energy", "Thermal", "Cost", "Charge", "Volume", "Mass"}
    assert len(body["matrix"]["rows"]) == 3 and "charge_time_derated_min" in body["matrix"]["metrics"]


def test_compare_custom_design_has_no_round1_targets(client, presets):
    edited = presets[2] | {"n_parallel": 13}
    body = client.post("/api/v1/compare", json={"designs": [presets[0], edited]}).json()
    by_id = {d["design"]["id"]: d for d in body["designs"]}
    assert by_id["option_b"]["round1_comparison"] == []      # edited preset is no longer the Round-1 design
    assert by_id["baseline"]["round1_comparison"]


@pytest.mark.parametrize("patch,code", [
    ({"n_series": 0}, 422),                    # schema validation
    ({"typo": 1}, 422),                        # extra fields rejected
    ({"cell_id": "no_such_cell"}, 404),        # unknown datasheet id
])
def test_bad_requests(client, presets, patch, code):
    r = client.post("/api/v1/simulate", json={"design": presets[0] | patch})
    assert r.status_code == code, r.text


def test_duplicate_ids_rejected(client, presets):
    r = client.post("/api/v1/compare", json={"designs": [presets[0], presets[0]]})
    assert r.status_code == 422 and "unique" in r.json()["detail"]
