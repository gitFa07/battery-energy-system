# PackForge — battery design workbench

Hackathon entry for **TELIPORT Season 4 (Tata Elxsi), Case Study 2: "Reusable Digital Platform for Designing
Battery Energy System"**. Brief: `Case Study 2_IDV_Battery_Energy_System.pdf`. Plan and status: `ROADMAP.md`.

The platform is generic (any cell, S×P layout, cooling, sensing, protection, control); the demo is one study:
a 48 V e-scooter pack at 40 °C ambient, charged right after a ride — baseline vs options A/B/C. Say *pack*, not
module (see `GLOSSARY.md`).

## Judging weights (optimise for these)
Technical feasibility 20 · Problem understanding 15 · Desirability 15 · Engineering quality 15 ·
Prototype & evidence 15 · Innovation 10 · Business viability 10.
→ A small, working, *validated* tool beats a large, vague one. Every number needs a stated source or assumption.

## Commands (Windows; use the venv)
```
python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/streamlit run app.py                                  # UI
.venv/Scripts/python -m packforge [study_dir] [--mc N] [--report out.html]   # CLI comparison / report
.venv/Scripts/python -m packforge.fit <log.csv> --cell <id> [--save]          # fit cell model to a test log
.venv/Scripts/python scripts/make_synthetic_log.py                  # regenerate the synthetic method-check log
PYTHONPATH=scripts .venv/Scripts/python scripts/calibrate_nmc.py    # NMC calibration + hold-out (~15 min, needs dataset.zip)
.venv/Scripts/python -m pytest -q                                   # ~90 s (fit test ~25 s)
```
pytest 9.2.0 crashes with `INTERNALERROR ... NodeId ... _str_cache` here — keep `pytest<9.2` (pinned).
Scripts that print must call `sys.stdout.reconfigure(encoding="utf-8")` — output contains °C, ₹, Δ.

## Layout
```
packforge/
  schema.py    pydantic models: Cell, Design (+ subsystems), Study, Requirement, Scenario, Assumption
  loader.py    JSON loading; `extends` deep-merge; cell referenced by id
  sim.py       batched electro-thermal time-domain sim + BMS control loop + hotspot observer (the physics)
  metrics.py   KPIs, METRICS registry (label, unit, evidence, model, subsystems), KPIS order, hand-calc bound
  checks.py    conflict checker: requirement checks + interface rules (IF-xx), with cause chain + fixes
  engine.py    run_scenarios (honours chains), run_design, monte_carlo, rank, recommend, traceability
  fit.py       fit cell params (+ r_temp_k, OCV) to measured logs by replaying them through sim.py; hold-out eval
  figures.py   plotly figures shared by UI and report
  ui.py        HTML for the UI: verdict headline, requirement grid (designs × checks), KPI table
  report.py    self-contained HTML design report
  __main__.py  CLI
app.py         Streamlit UI (Compare · Time series · Heat map · Conflicts · Traceability · Monte Carlo · Validation)
.streamlit/    theme (deck colours, light + dark) and bundled Barlow fonts from static/fonts/ (OFL)
data/cells/    cell JSON (id = filename); `<id>_fitted.json` from `fit --save`; `<id>_uncalibrated.json` = pre-calibration
data/validation/  logs (CSV: time_s, current_a [+ = discharge], voltage_v, temp_c [, temp_core_c, soc, ambient_c]),
               `calibration_<cell id>.json` (fit + hold-out record, read by UI/report), SOURCES.md (licences)
data/raw/      downloaded datasets (untrusted; read with `python -I`) and their conversions — not committed
studies/<name>/   study.json + one JSON per design option (sorted by filename; baseline first)
scripts/       one-off generators;  tests/
```

## Data flow
`study.json` + design JSONs → `loader` → `Design` (single source of truth) → `build_pack` samples per-cell
variation → `run_scenarios` (drive, then charge seeded from the drive's end state) → `all_metrics` →
`run_checks` → `rank` / `traceability` / `build_report`. Subsystem models exchange values only through `Design`
and the metrics dict — that is the "consistent parameter exchange" the brief asks for. Keep it that way.

## Model conventions (don't break)
- **Current > 0 = discharge.** Arrays are `(N samples, S series groups, P parallel cells)`. Per-cell params
  (`cap_ah`, `r0`, `r1`, `tau_s`, optionally `g_sink`) are per-sample arrays — `fit.py` relies on this to
  evaluate a whole finite-difference Jacobian as one batch.
- Cell: OCV(SOC) table + R0 + one RC branch; R0/R1 scale by Arrhenius(`r_temp_k`). Parallel cells share
  terminal voltage; series groups share current. OCV has steep tails beyond 0/100 % SOC (`TAIL_SLOPE_V`) —
  without them a flat LFP curve never reaches CV and packs drain past empty.
- Thermal: one node per cell; heat = I²R0 + V_rc²/R1; loss to sink via `h_eff × cell surface`
  (× `edge_factor` on the perimeter); 4-neighbour conduction `g_neighbor_w_k`.
- **BMS sees only its sensors.** `derate_on: sensed` derates on the hottest NTC; `observer` runs a
  nominal-parameter copy of the thermal network (equal current sharing, `observer_h_error` model error) pulled
  towards the NTCs, and derates on its hotspot. OT protection always uses real NTCs. `sensor_blind_spot_c` =
  true hottest cell − what the BMS derates on.
- Scenario types: `charge` (CC-CV + derating), `drive` (repeating power profile, W), `current` (imposed current,
  A — used to replay logs). `after: "<scenario>"` starts from that scenario's end state (start_soc ignored).
  Finished samples are frozen so end states are well defined.
- Plugging in above the derate window is a **thermal hold** (zero current until released), not a trip; an OT
  trip only fires while charge current flows. `t_max_charge_c` / `heat_w_charge` count only current-flowing steps.
- Headline charging KPI is `charge_time_min` = plug-in → 80 % incl. `thermal_hold_min`; `charge_time_10_80_min`
  excludes the hold and is secondary (industry comparison only).
- Log replays (`fit.predict`) start from the logged temperature and SOC; `ambient_c` in the log sets the chamber.
  `h_eff_w_m2k` and `c_th_j_k` (cell + fixture) are test-rig fit parameters — never written to a cell.
- `Cell.heat_factor` (default 1) multiplies heat in the real cells only; the observer and BMS don't know it.
  `engine.with_heat_factor` drives the robustness re-run (hold-out under-predicts the temperature rise ~2×).
- Default `dt = 2 s` (RC integrated exactly; thermal τ ≫ dt). Checked vs 1 s: KPIs within 0.4 %, ΔT within
  0.05 K. Re-check after any change to `sim.py`.
- `charge_time_bound_min` is an independent hand calc: the ideal profile for an interior cell from ambient (full
  current until the charge limit, then the current that holds it there). On a cold start the sim must stay within
  0.95–1.3× of it (slower by the derate-window margin, never much faster) — a test enforces this.
- Units are in field names (`_c`, `_k`, `_w`, `_wh`, `_ohm`, `_inr`, `_kg`, `_l`). Costs in ₹.

## Traceability and evidence rules
- Every placeholder or modelling choice gets an `Assumption` (id, text, source, `affects`) in the cell or design
  JSON; traceability links requirements → metrics → assumptions through the `affects` tags.
- Evidence ladder per metric: `datasheet < assumption < calculated < estimated < simulated < measured`.
  Upgrade to `measured` only with real rig or public-dataset logs.
- Logs named `SYNTHETIC_*` are generated by our own model — a method check for `fit.py`, **never** evidence.
  Never present them as validation.
- Cell numbers are generic "class" values, not a named datasheet — say so; never claim a specific part's spec.
- The NMC cell is calibrated on a **proxy cell** (LG M50LT, public TU Berlin dataset): call that evidence
  "measured (proxy)", fit at 25/35 °C, hold-out at 45 °C. Only cell-intrinsic parameters transfer — never the
  chamber h_eff. The LFP cell is **not validated**; say so wherever a result depends on it.
- Hold-out logs must never enter a fit; report voltage RMSE for SOC ≥ 10 % and full range side by side.
- `recommend()` gives up to three answers (best eligible; best that meets the should-reqs the best one misses;
  firmware-only retrofit of the first/baseline design). Never claim AIS-156 compliance for any design.

## How to extend
- **New cell:** add `data/cells/<id>.json` (copy one; fill `sources` and `assumptions`), or fit one from a log.
- **New option:** `studies/<study>/option_x.json` with `"extends": "baseline.json"` and only the diffs.
  Assumptions accumulate across `extends`; everything else deep-merges.
- **New requirement:** add to `study.json` (`metric` must be in `METRICS`); add an `EXPLAIN` entry in
  `checks.py` so failures show a cause chain and fixes.
- **New interface rule:** add a tuple to `interface_checks` (`IF-nn`, subsystems, ok, critical, detail, fixes).
  `critical=True` → fail (disqualifies in ranking); else warn.
- **New metric:** compute in `metrics.py`, register in `METRICS`, add to `KPIS` if it belongs in tables.
- New physics goes in `sim.py`, keeps the batch dimension, and must keep the energy/heat-balance tests passing.

## Tests that guard the physics (`tests/test_packforge.py`)
Energy 0.9–1.06× nominal ending on UV · charge ends on CV at the CV voltage · adiabatic heat balance ±2 % ·
chained charge starts from drive end state · hot plug-in fails baseline REQ-03 but passes cold and with Option C ·
observer stays ≤ 45 °C at ±30 % model error · sim vs hand-calc bound · conflict detection (IF-01, OT trip → IF-14) ·
ranking puts eligible designs first · MC batch == single run · fit recovers synthetic params (from the
`_uncalibrated` cell) · calibrated cell predicts two 45 °C hold-out logs · charge time ≥ hold + 10–80 % ·
recommend() roles · replay starts hot · extra heat only makes designs hotter · report content · UI grid/verdict.
Add a test for every new rule or model.

## Style
- Python 3.10, type hints, `from __future__ import annotations`, numpy vectorised (no per-cell Python loops).
- Short module docstrings stating the model/equations; comments only for non-obvious physics.
- Keep the UI thin: logic in `packforge/`, figures in `figures.py`, HTML in `ui.py`; `app.py` only renders.
  In `ui.py` colours come from `currentColor` so markup reads on both themes; only failures get colour.
- Cache in the UI with `st.cache_data` keyed on `model_dump_json()`; use `width="stretch"`, not
  `use_container_width`.

## Safety (hardware rig, see ROADMAP)
Low-voltage only (≤ 2S), protected cells, inline fuse, fireproof bag, never unattended, hard cutoffs in firmware.
Document every precaution — it is scored.
