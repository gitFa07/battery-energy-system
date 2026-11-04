"""VoltTwin Phase 1: datasheets load, validate, round-trip through SQLite, and presets are consistent."""

from __future__ import annotations

import pytest

from src.config import REQUIREMENTS, REQUIREMENTS_BY_ID
from src.models.db import CATALOGUE, DatasheetDB, load_json
from src.models.schemas import CoolingSpec, ModuleDesignInput, ModuleSimulationResult


@pytest.fixture(scope="module")
def db():
    d = DatasheetDB()
    yield d
    d.close()


@pytest.mark.parametrize("table", list(CATALOGUE))
def test_sqlite_round_trip_equals_json(db, table):
    file, key, model = CATALOGUE[table]
    from_json = [model.model_validate(item) for item in load_json(file)[key]]
    assert from_json and db._all(table, model) == from_json


def test_every_spec_states_a_source(db):
    specs = [*db.list_cells(), *db.list_cooling(), *db.list_busbars(), *db.list_protection(), *db.get_presets()]
    assert all(s.source.strip() for s in specs)


def test_seed_values_match_task_md(db):
    nmc, lfp = db.get_cell("nmc21700_4p8ah"), db.get_cell("lfp21700_3p8ah")
    assert (nmc.v_nom_v, nmc.capacity_ah, nmc.r0_ohm, nmc.mass_kg, nmc.cost_usd) == (3.65, 4.8, 0.018, 0.068, 1.35)
    assert (lfp.v_nom_v, lfp.capacity_ah, lfp.r0_ohm, lfp.mass_kg, lfp.cost_usd) == (3.20, 3.8, 0.022, 0.072, 0.92)
    assert {c.id for c in db.list_cooling()} == {"passive_air", "forced_air_fan", "al_fin_pcm"}
    assert {b.id for b in db.list_busbars()} == {"ni_strip_015mm", "cu_busbar_015mm"}


def test_cooling_dissipation_consistent_with_resistance(db):
    for c in db.list_cooling():
        assert c.q_dissipation_w == pytest.approx(10.0 / c.r_th_k_w, rel=0.01), c.id


def test_pcm_fields_must_come_together():
    with pytest.raises(ValueError, match="PCM"):
        CoolingSpec(id="x", name="x", source="t", kind="conduction_pcm", r_th_k_w=0.1, q_dissipation_w=100,
                    fan_power_w=0, pcm_mass_kg=1.0, pcm_latent_j_kg=0, pcm_melt_c=None, mass_kg=1, volume_l=1,
                    cost_usd=1)


def test_unknown_id_raises(db):
    with pytest.raises(KeyError):
        db.get_cell("nope")


def test_presets_reference_existing_specs(db):
    protection = {p.id: p for p in db.list_protection()}
    for p in db.get_presets():
        db.get_cell(p.cell_id), db.get_cooling(p.cooling_id), db.get_busbar(p.busbar_id)
        assert protection[p.fuse_id].kind in ("fuse", "pyro_fuse")
        assert protection[p.bms_id].kind == "bms"
        assert p.n_ntc <= protection[p.bms_id].ntc_channels, f"{p.id}: more NTCs than BMS inputs"


def test_preset_topologies(db):
    presets = {p.id: p for p in db.get_presets()}
    assert [p.id for p in db.get_presets()] == ["baseline", "option_a", "option_b"]
    assert {k: (p.n_series, p.n_parallel, p.n_cells) for k, p in presets.items()} == {
        "baseline": (13, 12, 156), "option_a": (15, 14, 210), "option_b": (13, 12, 156)}


def test_nominal_energy_covers_target_usable_energy(db):
    targets = db.get_targets()
    for p in db.get_presets():
        nominal_kwh = p.n_cells * db.get_cell(p.cell_id).energy_wh / 1000
        assert nominal_kwh >= targets[p.id]["usable_energy_kwh"], p.id
        assert nominal_kwh * p.usable_dod == pytest.approx(targets[p.id]["usable_energy_kwh"], rel=0.10), p.id


def test_targets_cover_every_preset_and_known_requirements(db):
    targets = db.get_targets()
    assert set(targets) == {p.id for p in db.get_presets()}
    for t in targets.values():
        assert set(t["status"]) <= set(REQUIREMENTS_BY_ID)
        assert t["verdict"] in ("OPTIMAL", "REJECTED", "UNSAFE")


def test_seven_hard_requirements_point_at_result_fields():
    assert [r.id for r in REQUIREMENTS] == ["REQ-EL-01", "REQ-EL-02", "REQ-TH-01", "REQ-CH-01", "REQ-ME-01",
                                            "REQ-ME-02", "REQ-EC-01"]
    assert {r.metric for r in REQUIREMENTS} <= set(ModuleSimulationResult.model_fields)
    el = REQUIREMENTS_BY_ID["REQ-EL-01"]
    assert (el.status(48.0), el.status(43.9), el.status(54.1)) == ("PASS", "FAIL", "FAIL")


def test_extra_fields_rejected(db):
    data = db.get_presets()[0].model_dump() | {"typo_field": 1}
    with pytest.raises(ValueError):
        ModuleDesignInput.model_validate(data)


def test_file_backed_db_persists(tmp_path):
    path = tmp_path / "volttwin.db"
    DatasheetDB(path).close()
    reopened = DatasheetDB(path, seed=False)
    assert len(reopened.list_cells()) == 2
    reopened.close()
