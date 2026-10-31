<div align="center">

# 🔋 PackForge

**A reusable cell-to-pack battery design workbench: simulate design options against an application's
requirements, find the conflicts between subsystems, and recommend one with its risks stated.**

![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![Tests](https://img.shields.io/badge/tests-23%20passing-2ea44f)
![Data](https://img.shields.io/badge/validation%20data-CC%20BY%204.0-lightgrey)

[Overview](#overview) · [Key results](#key-results) · [Getting started](#getting-started) ·
[Usage](#usage) · [How it works](#how-it-works) · [Evidence](#evidence-and-validation) ·
[Extending](#extending-packforge)

</div>

## Overview

PackForge was built for **TELIPORT Season 4 (Tata Elxsi), Case Study 2: "Reusable Digital Platform for Designing
Battery Energy System"**. The platform is generic: any cell, any S×P layout, cooling, sensing, protection and BMS
control. The example study is one hard case: a **48 V e-scooter pack at 40 °C ambient, charged right after a
ride**.

That case shows why cell-level modelling matters. After a ride, the baseline pack's two edge NTCs cool first and
read the hottest cell 3.2 K low. The BMS waits 48 min, then charges interior cells at 47.6 °C, above their 45 °C
limit. Nothing on the BMS shows it. PackForge finds this before any hardware is built, explains the cause, and
compares fixes.

What it does:

- **Electro-thermal simulation** of every cell in the pack, with a BMS control loop (CC-CV, derating, OV/UV/OT
  protection) that sees only its sensors.
- **Conflict checker**: 11 requirements and 14 interface rules. Each failure comes with a cause chain across
  subsystems and candidate fixes.
- **Sensor blind-spot detection**: how far the hottest cell runs above what the BMS acts on.
- **Virtual hotspot sensor**: a BMS-side thermal observer, offered as a ₹0 firmware retrofit.
- **Three-part recommendation**: the best eligible design, the best one that meets the targets the first one
  misses, and a firmware-only retrofit for packs already built.
- **Robustness re-run** with extra heat that the BMS is not told about. Monte Carlo cell-to-cell variation.
- **Evidence-ladder traceability**: requirement → metric → assumption. Every number is tagged from *datasheet*
  up to *measured*.
- **Cell model fitting** from measured logs, with a hold-out check on data the fit never saw.
- Streamlit UI, CLI, and a self-contained offline HTML report, all built on one core.

## Key results

E-scooter study, 40 °C ambient, plugged in right after the ride. All values come from
`python -m packforge`.

| | Baseline: NMC passive | A: NMC + Al plate | B: LFP 16S8P | C: baseline + observer |
|---|---|---|---|---|
| **Charge time (plug-in → 80 %)** | 244 min | 92 min | 97 min | 277 min |
| of which thermal hold | 48 min | 0 | 0 | 90 min |
| Peak cell temperature while charging | **47.6 °C (fails)** | 44.0 °C | 43.7 °C | 44.5 °C |
| Hottest cell − BMS view | 3.2 K | 0.0 K | 0.1 K | 0.2 K |
| Mass | 12.3 kg | 13.5 kg | 22.7 kg | 12.3 kg |
| ₹ per usable kWh | 23.1 k | 24.8 k | 18.2 k | 23.1 k |
| Est. cycle life | ~370 | ~405 | ~1,290 | ~370 |
| **Ranking** | disqualified | 2nd | **1st** | 3rd |

**Recommendation:** **B** (LFP) for new packs. **A** if mass and volume are hard limits. **C** as a ₹0 firmware
retrofit for 2-NTC packs already built. C is safe but slower after a hot ride.

> [!WARNING]
> The LFP cell behind the recommended design is **not validated**. If cells make 2× the modelled heat, B misses
> the charge limit by 0.02 K and A becomes the pick. The next step is one LFP charge test through the same fit
> pipeline. No design is claimed to be AIS-156 compliant.

## Getting started

### Prerequisites

- Python 3.10 or later
- Windows commands are shown. On Linux/macOS use `.venv/bin/` instead of `.venv/Scripts/`.

### Install

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
```

> [!NOTE]
> `pytest` is pinned below 9.2 because 9.2.0 crashes with an `INTERNALERROR` in this setup.

## Usage

### Workbench UI

```bash
.venv/Scripts/streamlit run app.py
```

The sidebar picks the study and designs. It also sets ambient temperature, whether the charge starts right after
the ride, and the **Unmodelled heat ×** factor. A what-if panel varies parallel count, C-rate, derating window,
cooling and sensor layout.

| Tab | Shows |
|---|---|
| Compare | KPI table with evidence levels, trade-off radar, ranking |
| Time series | Charge and drive signals per design, with BMS events |
| Heat map | Cell temperatures at the peak, with BMS sensor positions |
| Conflicts | Failures and warnings with cause chains and candidate fixes |
| Traceability | Requirement → metric → assumption matrix, design JSON download |
| Monte Carlo | Spread of energy, charge time and peak temperature over sampled packs |
| Validation | Calibration and hold-out results, log replay, fit your own log |

### Command line

```bash
# Compare all designs in a study, print conflicts, ranking, recommendations and the 2x heat re-run
.venv/Scripts/python -m packforge studies/escooter_48v --report packforge_report.html

# Options: --mc N (Monte Carlo samples per design), --stress F (unmodelled-heat factor, 1 = off)

# Fit a cell model to a measured log (current > 0 = discharge)
.venv/Scripts/python -m packforge.fit data/validation/<log>.csv --cell nmc21700_5ah [--free r_temp_k ocv] [--save]
```

> [!TIP]
> The whole e-scooter study, including the robustness re-run, takes about 30 s on a laptop. The report is a
> single offline HTML file with every figure embedded.

### Tests

```bash
.venv/Scripts/python -m pytest -q   # ~90 s
```

The tests check energy and heat balance, CC-CV behaviour and chained scenarios. They compare the simulation with
an independent hand-calc bound and check the observer at ±30 % model error. They also cover conflict detection,
ranking, Monte Carlo batching, fit recovery, the hold-out prediction, the recommendation roles and the report
content.

## How it works

```
study.json + design JSONs ─► loader ─► Design (single source of truth)
   ─► sim: drive, then charge from the drive's end state (per-cell electro-thermal + BMS loop)
   ─► metrics (KPIs + evidence level) ─► checks (requirements + interface rules)
   ─► rank · recommend · traceability · report
```

Subsystem models exchange values only through the `Design` and the metrics dict. This is the brief's "consistent
parameter exchange".

- **Cell:** OCV(SOC) table + R0 + one RC branch. Resistances scale with temperature (Arrhenius).
- **Thermal:** one node per cell. Heat is I²R0 + V_rc²/R1. Heat leaves to the sink through an effective h over
  the cell surface (more at the pack edge) and conducts to 4 neighbours.
- **BMS:** derates on its hottest NTC, or on an observer that runs a nominal thermal model corrected by the NTCs.
  Plugging in above the derate window is a *thermal hold*, not a trip.
- **Sanity checks:** a 2 s time step (KPIs within 0.4 % of 1 s), an adiabatic heat balance within ±2 %, and a
  hand-calc thermal-limit bound that the simulation must track.

```
packforge/   schema · loader · sim · metrics · checks · engine · fit · figures · report · CLI
app.py       Streamlit UI (rendering only)
data/cells/  cell JSON (id = file name)          studies/<name>/  study.json + one JSON per design option
data/validation/  logs, calibration record, SOURCES.md          scripts/  data conversion and calibration
docs/        demo script and offline backups      tests/  physics, checks, calibration, recommendations
```

## Evidence and validation

The NMC cell is calibrated on a **proxy cell**: the LG INR21700 M50LT, from the public TU Berlin *Lithium-Ion
Battery Internal Temperature Dataset*. It is fitted at 25 and 35 °C and checked on **60 hold-out logs at
45 °C** that the fit never saw.

| Hold-out set | Logs | V RMSE, SOC ≥ 10 % (median / max) | T RMSE (median) | T rise meas / model |
|---|---|---|---|---|
| Drive cycles | 30 | 18 / 43 mV | 0.23 K | 2.0 / 1.0 K |
| 1C charges | 30 | 17 / 22 mV | 0.55 K | 3.4 / 1.6 K |

The voltage holds at a temperature the fit never saw. The temperature rise is under-predicted about 2×, so every
design is also run with 2× unmodelled heat.

> [!IMPORTANT]
> - Proxy-cell results are labelled *measured (proxy)*. Only cell-intrinsic parameters transfer to a pack. The
>   test rig's chamber cooling is never transferred.
> - LFP values, costs and masses are generic class values, not a named datasheet.
> - `SYNTHETIC_*` logs are generated by PackForge's own model. They are a method check for the fitter, never
>   evidence.

To reproduce the calibration (about 15 min), download the dataset as described in
[`data/validation/SOURCES.md`](data/validation/SOURCES.md), then run:

```bash
PYTHONPATH=scripts .venv/Scripts/python scripts/calibrate_nmc.py
```

Known limitations are listed in [`ROADMAP.md`](ROADMAP.md#known-limitations-state-them-openly).

## Extending PackForge

| To add | Do this |
|---|---|
| A cell | Copy a file in `data/cells/` and fill in `sources` and `assumptions`, or fit one from a log with `packforge.fit --save` |
| A design option | Add `studies/<study>/option_x.json` with `"extends": "baseline.json"` and only the differences |
| A study | Add `studies/<name>/study.json` (application, ambient, scenarios, requirements, score weights) plus design files |
| A requirement | Add it to `study.json` (its `metric` must be in `METRICS`) and an `EXPLAIN` entry in `checks.py` |
| An interface rule | Add an `IF-nn` tuple to `interface_checks` in `checks.py`. `critical=True` disqualifies |

A design option only needs its differences from the baseline:

```json
{
  "extends": "baseline.json",
  "id": "option_c",
  "name": "Option C — baseline + virtual hotspot sensor",
  "control": {"charge_c_rate": 0.95, "derate_on": "observer", "derate_start_c": 43.5, "derate_end_c": 44.5},
  "assumptions": [
    {"id": "A-C1", "text": "BMS MCU can run a 130-node thermal model at 0.5 Hz (no BOM change)", "affects": ["control", "cost"]}
  ]
}
```

## Resources

- [`ROADMAP.md`](ROADMAP.md): status, full results, pitch storyline, limitations and risks
- [`GLOSSARY.md`](GLOSSARY.md): project terms (pack, blind spot, thermal hold, charge time, proxy cell…)
- [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md): timed live-demo walkthrough and backup-clip shot list
- [`data/validation/SOURCES.md`](data/validation/SOURCES.md): dataset attribution. Yao, Droese, Kowal, TU Berlin,
  DOI [10.14279/depositonce-25110](https://doi.org/10.14279/depositonce-25110),
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
