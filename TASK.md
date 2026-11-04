# Battery Energy System Studio (VoltTwin Studio) — Implementation Tasks & Tracker

**Project:** Battery Energy System Studio (VoltTwin Studio)  
**Event:** Tata Elxsi TELIPORT Season 4 Hackathon — Round 2  
**Case Study:** Case Study 2 — Reusable Digital Platform for Designing Battery Energy System  
**Role:** Principal Battery Systems Architect & Full-Stack Python Engineer  

---

## 1. System Requirements & Benchmark Target References

### 1.1 Hard Requirements Traceability Matrix
- [ ] `REQ-EL-01`: Nominal Voltage Window $48.0\text{ V}$ ($44.0\text{ V}$ to $54.0\text{ V}$) — *Cutoff: Outside inverter/controller limits*
- [ ] `REQ-EL-02`: Usable Energy $\ge 2.40\text{ kWh}$ ($100\%$ to $0\%$ or designated DoD window) — *Cutoff: Insufficient range (< 2.40 kWh)*
- [ ] `REQ-TH-01`: Peak Cell Temperature $\le 50.0^\circ\text{C}$ at $40.0^\circ\text{C}$ ambient — *Cutoff: BMS thermal cutoff at 55.0°C*
- [ ] `REQ-CH-01`: Fast Charge Turnaround ($10\%$ to $80\%$ SoC) $\le 45.0\text{ min}$ — *Cutoff: Exceeds turnaround window*
- [ ] `REQ-ME-01`: Module Total Mass $\le 18.0\text{ kg}$ — *Cutoff: Exceeds e-scooter chassis structural envelope*
- [ ] `REQ-ME-02`: Module Volume / Size $\le 12.0\text{ L}$ — *Cutoff: Exceeds under-seat bay envelope*
- [ ] `REQ-EC-01`: Target BOM Cost $\le \$360.00$ — *Cutoff: Exceeds commercial unit cost ceiling*

### 1.2 Reference Benchmark Presets (Round 1 Submission Targets)
| Metric | Starting Baseline | Design Option A | Design Option B (Recommended) |
|---|---|---|---|
| **Cell & Topology** | NMC 21700 ($13\text{S-}12\text{P}$, 156 cells) | LFP 21700 ($15\text{S-}14\text{P}$, 210 cells) | NMC 21700 ($13\text{S-}12\text{P}$, 156 cells) |
| **Cooling Method** | Passive Natural Air Enclosure | Forced Air Duct + 12V Axial Fan | Al-Fin Conduction + PCM Matrix |
| **Interconnect & Protection** | Ni-strip, 4x NTC, 100A Fuse, Basic BMS | Cu-busbar, 6x NTC, 100A Fuse, Fan PWM BMS | Cu-busbar, 8x NTC, 120A Pyro-Fuse, Active BMS |
| **Usable Energy** | $2.52\text{ kWh}$ (`PASS`) | $2.45\text{ kWh}$ (`PASS`) | $2.52\text{ kWh}$ (`PASS`) |
| **Peak Cell Temp** | $58.4^\circ\text{C}$ (`FAIL`: $> 50.0^\circ\text{C}$) | $43.1^\circ\text{C}$ (`PASS`) | $44.2^\circ\text{C}$ (`PASS`) |
| **Fast Charge (10–80%)** | $42\text{ min}$ (derated to $68\text{ min}$) | $44\text{ min}$ (`PASS`) | $39\text{ min}$ (`PASS`) |
| **Module Mass** | $13.8\text{ kg}$ (`PASS`) | $19.6\text{ kg}$ (`FAIL`: $> 18.0\text{ kg}$) | $15.4\text{ kg}$ (`PASS`) |
| **Module Volume** | $9.2\text{ L}$ (`PASS`) | $12.8\text{ L}$ (`FAIL`: $> 12.0\text{ L}$) | $10.1\text{ L}$ (`PASS`) |
| **Est. BOM Cost** | $\$310$ (`PASS`) | $\$275$ (`PASS`) | $\$345$ (`PASS`) |
| **Verdict** | `UNSAFE: Thermal Violation` | `REJECTED: Mass/Size Conflict` | `OPTIMAL: Balanced Design` |

---

## 2. Phase-by-Phase Execution Tracker

### Phase 1: Project Scaffolding, Schemas & Verified Datasheet Layer
- **Status:** Pending
- **Objective:** Establish the Python packaging structure, Pydantic v2 data schemas, hard requirement thresholds, and SQLite/JSON datasheet seed layer.
- **Sub-tasks:**
  - [ ] Initialize / update `pyproject.toml` and dependencies (`fastapi`, `uvicorn`, `pydantic>=2.7`, `numpy`, `scipy`, `pandas`, `plotly`, `streamlit`, `pybamm`, `pytest`, `httpx`).
    - *Target File:* `pyproject.toml`
  - [ ] Define system configuration and 7 hard requirements (`REQ-EL-01` to `REQ-EC-01`), ambient defaults ($40.0^\circ\text{C}$ ref, $55.0^\circ\text{C}$ BMS cutoff).
    - *Target File:* `src/config.py`
  - [ ] Seed cell specifications for NMC 21700 ($3.65\text{ V}, 4.8\text{ Ah}, 18.0\text{ m}\Omega, 68\text{ g}, \$1.35$) and LFP 21700 ($3.20\text{ V}, 3.8\text{ Ah}, 22.0\text{ m}\Omega, 72\text{ g}, \$0.92$).
    - *Target File:* `data/datasheets/cells_liiondb.json`
  - [ ] Seed cooling topologies (`passive_air`, `forced_air_fan`, `al_fin_pcm`) with thermal resistance, heat dissipation capacity, parasitic mass, volume, and cost.
    - *Target File:* `data/datasheets/cooling_topologies.json`
  - [ ] Seed interconnects and protection specs (`ni_strip_015mm`, `cu_busbar_015mm`, NTC sensors, fuses, BMS options).
    - *Target File:* `data/datasheets/busbars_protection.json`
  - [ ] Seed 3-way reference benchmark presets (Baseline, Option A, Option B).
    - *Target File:* `data/datasheets/presets_three_way.json`
  - [ ] Implement Pydantic v2 domain schemas (`CellSpec`, `CoolingSpec`, `BusbarSpec`, `ProtectionSpec`, `ModuleDesignInput`, `ModuleSimulationResult`, `TraceabilityRecord`).
    - *Target File:* `src/models/schemas.py`
  - [ ] Implement SQLite datasheet repository and database loader (`db.py`).
    - *Target File:* `src/models/db.py`
  - [ ] Create package initialization files.
    - *Target Files:* `src/__init__.py`, `src/models/__init__.py`
- **Verification Commands:**
  - [ ] `pytest tests/test_datasheets.py -v` (Verify clean loading, schema validation, and preset parameter integrity)

---

### Phase 2: Coupled Multi-Physics Simulation Engine (PyBaMM + Interconnect + Thermal + BOM)
- **Status:** Pending
- **Objective:** Construct the electro-chemical, ohmic, thermal, mechanical, and cost physics models with dynamic recalculation and dual-mode PyBaMM execution.
- **Sub-tasks:**
  - [ ] Implement PyBaMM runner supporting SPMe + lumped thermal model (`Marquis2019` for NMC, `Prada2013` for LFP) with fast-solve calibrated surrogate fallback.
    - *Target File:* `src/physics/pybamm_runner.py`
  - [ ] Implement electrical physics module: $N_s \times N_p$ topology sizing, nominal/cutoff voltages, usable energy ($\eta_{\text{DoD}}$), $15\%$ BoL internal resistance ageing margin, and pack-level busbar $I^2R$ heating.
    - *Target File:* `src/physics/electrical.py`
  - [ ] Implement thermal physics module: coupled cell reversible/irreversible heat + busbar ohmic heat vs. cooling rejection, PCM latent heat buffering, peak cell temperature $T_{\text{peak}}$, and thermal derating cutoff extending fast charge time.
    - *Target File:* `src/physics/thermal.py`
  - [ ] Implement mechanical and BOM cost module: cylindrical cell packing factor, duct/fin volume overhead, total pack mass, volume ($L$), and itemized BOM cost.
    - *Target File:* `src/physics/mechanical_bom.py`
  - [ ] Implement physics package initialization.
    - *Target File:* `src/physics/__init__.py`
- **Verification Commands:**
  - [ ] `pytest tests/test_physics_engine.py -v` (Verify Baseline: $2.52\text{ kWh}, 58.4^\circ\text{C}, 13.8\text{ kg}, \$310$; Option A: $2.45\text{ kWh}, 43.1^\circ\text{C}, 19.6\text{ kg}, \$275$; Option B: $2.52\text{ kWh}, 44.2^\circ\text{C}, 15.4\text{ kg}, \$345$)

---

### Phase 3: Interface Conflict Validator, Traceability Chain & TOPSIS Recommender
- **Status:** Pending
- **Objective:** Build deterministic cross-disciplinary conflict detection rules, the requirement-to-validation traceability graph, and TOPSIS multi-criteria decision engine.
- **Sub-tasks:**
  - [ ] Implement conflict detection engine with structured alert models (`CRITICAL`, `WARNING`, `PASS`) covering:
    - Rule 1: Thermal-Electrical Interface Conflict ($\dot{Q}_{\text{total}} > \dot{Q}_{\text{cooling}}$ or $T_{\text{peak}} > 50.0^\circ\text{C}$ causing derating).
    - Rule 2: Electro-Mechanical Packaging Conflict (cell count / chemistry mass $> 18.0\text{ kg}$ or volume $> 12.0\text{ L}$).
    - Rule 3: Protection & Sensing Interface Conflict (peak 2C discharge $>$ fuse rating, NTC count $< 6$ on high-density NMC).
    - *Target File:* `src/validator/conflict_engine.py`
  - [ ] Implement traceability builder linking: Requirement ID $\rightarrow$ Datasheet Parameter $\rightarrow$ Physics Model $\rightarrow$ Simulated Metric $\rightarrow$ Validation Reference.
    - *Target File:* `src/validator/traceability.py`
  - [ ] Implement margin-to-limit normalization (0–100 scale) for Radar axes and TOPSIS multi-criteria decision ranker producing automated verdicts (`OPTIMAL`, `REJECTED`, `UNSAFE`).
    - *Target File:* `src/validator/topsis_recommender.py`
  - [ ] Implement validator package initialization.
    - *Target File:* `src/validator/__init__.py`
- **Verification Commands:**
  - [ ] `pytest tests/test_conflict_validator.py -v` (Verify conflict alert triggers, radar margin scaling, TOPSIS ranking, and traceability link integrity)

---

### Phase 4: FastAPI Backend Service
- **Status:** Pending
- **Objective:** Expose the simulation, comparison, conflict validation, and traceability engines through documented REST API endpoints.
- **Sub-tasks:**
  - [ ] Implement FastAPI application with CORS, exception handling, and endpoints:
    - `GET /api/v1/health`: System health and engine status.
    - `GET /api/v1/datasheets`: Available cells, cooling topologies, busbars, BMS options, and requirements.
    - `POST /api/v1/simulate`: Run multi-physics simulation, conflict check, and traceability generation for any custom `ModuleDesignInput`.
    - `POST /api/v1/compare`: Multi-design comparison matrix, radar metrics, and TOPSIS recommendation.
    - *Target File:* `src/api/main.py`
  - [ ] Implement API package initialization.
    - *Target File:* `src/api/__init__.py`
  - [ ] Write integration test suite using `httpx.TestClient`.
    - *Target File:* `tests/test_api.py`
- **Verification Commands:**
  - [ ] `pytest tests/test_api.py -v` (Verify status codes, request validation, and JSON payload fidelity across all endpoints)

---

### Phase 5: Interactive Scenario Workbench (Streamlit + Plotly)
- **Status:** Pending
- **Objective:** Deliver an interactive digital engineering workbench featuring real-time sliders, Plotly visualization charts, 3-way benchmark comparison, and PyBaMM integration.
- **Sub-tasks:**
  - [ ] Implement 4 interactive Plotly figures:
    1. Trade-Off Radar Chart (Margin-to-Limit on Energy, Thermal, Cost, Charge, Volume, Mass).
    2. Electro-Thermal Fast-Charge Transient Curve (Temperature & Voltage vs. Time with $50^\circ\text{C}$ limit & $55^\circ\text{C}$ BMS cutoff).
    3. Heat Generation vs. Cooling Rejection Stacked Breakdown Bar Chart.
    4. BatteryArchive Validation Overlay (Empirical vs. Simulated transient curves).
    - *Target File:* `src/workbench/plots.py`
  - [ ] Synthesize empirical cycle validation data for BatteryArchive overlay.
    - *Target File:* `data/validation/battery_archive_cycles.csv`
  - [ ] Build comprehensive Streamlit user interface:
    - Top Header with Requirement Badges (`REQ-EL-01` to `REQ-EC-01`).
    - Sidebar Interactive Configurator (Chemistry, $N_s$, $N_p$, C-rate, Ambient Temp, Cooling, Busbar, NTC/BMS, and live PyBaMM ODE toggle).
    - Main Workspace Tabs:
      - Tab 1: 3-Way Design Comparison & Trade-Off Radar.
      - Tab 2: Coupled Multi-Physics & PyBaMM Curves.
      - Tab 3: Interface Conflict & Safety Validator.
      - Tab 4: End-to-End Traceability & Low-Voltage ($1\text{S-}4\text{P}$) Validation.
    - *Target File:* `src/workbench/app.py`
  - [ ] Implement workbench package initialization.
    - *Target File:* `src/workbench/__init__.py`
- **Verification Commands:**
  - [ ] `streamlit run src/workbench/app.py --server.headless true` (Smoke test for clean execution without runtime errors)

---

### Phase 6: Automated Compliance Report Exporter & Low-Voltage (1S-4P) Validation Module
- **Status:** Pending
- **Objective:** Add one-click export of an engineering compliance report and a scaled $1\text{S-}4\text{P}$ low-voltage bench test protocol.
- **Sub-tasks:**
  - [ ] Implement report generator exporting Markdown / HTML Battery System Design & Safety Traceability Report:
    - Selected architecture and BOM breakdown.
    - Requirements compliance status matrix.
    - Active interface conflicts and documented model assumptions ($15\%$ ageing margin, uniform contact resistance, 1D lumped vs. 3D CFD limitations).
    - Scaled $1\text{S-}4\text{P}$ Safe Low-Voltage ($3.65\text{ V}, 19.2\text{ Ah}$) Bench Test Protocol (load resistor/current parameters, 8-point NTC placement, expected $\Delta T$).
    - *Target File:* `src/workbench/report_generator.py`
  - [ ] Implement unit tests for report generation and $1\text{S-}4\text{P}$ test calculation.
    - *Target File:* `tests/test_report_generator.py`
- **Verification Commands:**
  - [ ] `pytest tests/test_report_generator.py -v` (Verify complete report formatting and traceability ID inclusion)

---

### Phase 7: End-to-End Integration, Reproducibility Script & Round 2 Demo Readiness
- **Status:** Pending
- **Objective:** Ensure single-command reproducibility and automated demo execution for TELIPORT Round 2 judges.
- **Sub-tasks:**
  - [ ] Create automated demo runner script that seeds SQLite, runs benchmark verification, prints comparison and conflict summaries, and launches services.
    - *Target File:* `run_demo.py`
  - [ ] Update `README.md` with complete architecture guide, mathematical derivations, installation steps, and known limitations.
    - *Target File:* `README.md`
  - [ ] Run full end-to-end test suite across all subsystems.
- **Verification Commands:**
  - [ ] `pytest -v` (Confirm 100% test pass rate across all test modules)
  - [ ] `python run_demo.py --cli-only` (Verify automated CLI demonstration execution)

---

## 3. Overall Execution Summary
| Phase | Name | Scope | Status |
|---|---|---|---|
| **Phase 1** | Scaffolding, Schemas & Datasheets | Schemas, SQLite loader, LiionDB datasheets | **Pending** |
| **Phase 2** | Multi-Physics Engine | PyBaMM, Electrical, Thermal, Mechanical, BOM | **Pending** |
| **Phase 3** | Conflict & Traceability Engine | 3 Rules, Traceability Graph, TOPSIS | **Pending** |
| **Phase 4** | FastAPI Backend Service | REST Endpoints, API Tests | **Pending** |
| **Phase 5** | Interactive Scenario Workbench | Streamlit UI, 4 Plotly Charts | **Pending** |
| **Phase 6** | Compliance Report & 1S-4P Test | Report Generator, Scaled Lab Protocol | **Pending** |
| **Phase 7** | E2E Integration & Demo Readiness | `run_demo.py`, Full Documentation | **Pending** |

