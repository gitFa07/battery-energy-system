# ROADMAP — PackForge (TELIPORT S4, Case Study 2)

Goal: win on the rubric — a **small, working, validated** design workbench with a clear recommendation.
Priorities are ordered by judging weight × effort. Status: ✅ done · 🔜 next · ⬜ later · ✂️ cut if short on time.

## Where we are

**Phase 0 — core ✅**
- Design schema as single source of truth; options inherit from baseline via `extends`
- Electro-thermal sim (ECM 1-RC, per-cell thermal network) with BMS loop: CC-CV, derating, OV/UV/OT protection
- KPIs with evidence levels; requirement checks + 14 interface rules with cause chains and fixes
- Ranking/recommendation, traceability matrix, Monte Carlo cell variation (vectorised); Streamlit UI + CLI

**Phase 1/2 — delivered ✅**
- Chained scenarios: charge starts from the pack's end-of-ride state (default in the e-scooter study)
- Thermal hold at hot plug-in (BMS waits instead of tripping); charge KPIs count only current-flowing time
- Option C (software-only): BMS thermal observer ("virtual hotspot sensor"), robust to ±30 % model error
- Hand-calc thermal-limit bound (ideal profile: full current to the limit, then held there) cross-checks the sim
- HTML design report (CLI `--report`, UI download), fully offline (plotly embedded)

**Day 1–2 — evidence and decisions applied ✅**
- **NMC cell calibrated on a proxy cell** (LG M50LT, TU Berlin Internal Temperature Dataset, CC BY 4.0):
  OCV, R0, R1, τ, Arrhenius coefficient; capacity and OCV(100 %) measured. Fit at 25 + 35 °C on US06, HWFET and
  the 1C CC-CV charge; **hold-out at 45 °C** on 3 cells × (10 drives + 10 charges) never used in the fit.
- Chamber h_eff and fixture heat capacity are fitted as *test-rig* parameters and never transferred to packs.
- Headline KPI **charge time = plug-in → 80 % incl. thermal hold** (REQ-05 ≤ 120 min, should); hold shown apart.
- Options charge at their cell's limit: A and C 0.95C (NMC 4.9 A limit), B 1C (LFP 6 A).
- Three-part recommendation computed by `recommend()`; robustness re-run with 2× unmodelled heat (UI slider,
  report section, CLI `--stress`). 23 tests.

## Validation (proxy cell, hold-out at 45 °C)

| Hold-out set | Logs | V RMSE, SOC ≥ 10 % (median / max) | V RMSE, full range | T RMSE (median) | T rise meas / model |
|---|---|---|---|---|---|
| Drive cycles | 30 | 18 / 43 mV | 38 / 122 mV | 0.23 K | 2.0 / 1.0 K |
| 1C charges | 30 | 17 / 22 mV | 22 / 25 mV | 0.55 K | 3.4 / 1.6 K |

Calibrated vs generic: R0 0.0267 vs 0.020 Ω, R1 0.0230 vs 0.012 Ω, τ 46 vs 30 s, Ea/R 1672 vs 3000 K,
capacity 4.874 vs 5.0 Ah. Voltage — hence heat generation — holds at a temperature the fit never saw. **The
temperature rise is under-predicted ~2×**: heat rises with SOC during charge in the data, the 1-RC model has no
SOC-dependent resistance or entropic heat, and chamber data cannot separate missing heat from chamber cooling.
Hence the 2× robustness re-run. The core runs up to 4.6 K above the measured surface (one node per cell).

## Current e-scooter study (40 °C ambient, plugged in right after the ride, calibrated NMC cell)

| | Baseline NMC passive | A: NMC + Al plate | B: LFP 16S8P | C: baseline + observer |
|---|---|---|---|---|
| **Charge time (plug-in → 80 %)** | 244 min | 92 min | 97 min | 277 min |
| of which thermal hold | 48 min | 0 | 0 | 90 min |
| 10–80 % charge (excl. hold) | 161 min | 83 min | 88 min | 165 min |
| Peak cell T while charging | **47.6 °C ❌** | 44.0 °C | 43.7 °C | 44.5 °C |
| Peak cell T while riding | 53.4 °C | 44.1 °C | 43.1 °C | 53.4 °C |
| Hottest cell − BMS view | 3.2 K ⚠️ | 0.0 K | 0.1 K | 0.2 K |
| Mass | 12.3 kg | 13.5 kg | 22.7 kg ⚠️ | 12.3 kg |
| ₹ per usable kWh | 23.1 k | 24.8 k | 18.2 k | 23.1 k |
| Est. cycle life | ~370 | ~405 | ~1,290 | ~370 |
| Ranking | disqualified | 2nd | **1st** | 3rd |
| **With 2× unmodelled heat** | fails REQ-03, -04 (64 °C ride) | passes (45.0 °C), 132 min | **fails REQ-03 by 0.02 K**, 173 min | fails REQ-04 (64 °C ride) |

Calibration changed the numbers (hold 7 → 48 min, A 73 → 92 min), not the ranking. NMC packs warn IF-03 (fuse
margin): higher measured resistance → more current for the same power.

**Pitch storyline (all from the tool's own output):**
1. *Problem.* After a ride the baseline's edge NTCs cool first and under-read the hottest cell by 3.2 K. The BMS
   waits 48 min, then charges interior cells at 47.6 °C — above their 45 °C limit, invisible without cell-level
   modelling. This is the brief's "propagates unpredictably from cell to system".
2. *Physics limit.* At 40 °C ambient the 45 °C limit leaves 5 K of headroom; the hand calc puts a passive NMC
   pack at ≥ 139 min for 10→80 % even from a cold start, and the sim agrees. No firmware beats it.
3. *Evidence.* The cell model is calibrated on public measured data and checked on 60 logs it never saw.
4. *Three answers:*
   - **B** (LFP) recommended: cheapest per kWh, ~3× life, 97 min — but ~10 kg heavier and bulkier.
   - **A** (+₹2.7 k, +1.2 kg) if mass/volume are hard limits: 92 min, and the most robust to extra heat.
   - **C** (₹0, firmware) for 2-NTC packs already built: stops hot charging, but slower (277 min) because it
     honestly waits for the hotspot. Not AIS-156 compliant — the rule asks for ≥ 4 sensors.
5. *Top risk.* B's LFP cell is not validated; at 2× heat B fails the charge limit by 0.02 K and A becomes the
   pick. Next step: one LFP charge test (the same pipeline, one CSV).

## Phase 4 — Day 3: Demo & story 🔜 (Problem understanding 15 %, Desirability 15 %)

- ✅ **Pitch deck** (slides artifact, 18 slides, team edits) · **demo script + backup-clip shot list**
  (`docs/DEMO_SCRIPT.md`) · CLI output and offline report in `docs/backup/`
- ✅ Deck final: names and contacts filled, slides checked visually; 3 silent demo GIFs in `docs/backup/` (local)
- 🔜 Team: record the full backup clip (shot list in `docs/DEMO_SCRIPT.md`), rehearse, export the deck as PDF
- 🔜 **Live-demo path:**
  1. baseline after a ride → 48 min hold, then REQ-03 fails; heat map shows the interior hotspot vs edge NTCs
  2. Option C (observer) → passes, but slower — the honest trade-off
  3. compare A and B; three-part recommendation
  4. Validation tab: replay a 45 °C hold-out charge through the calibrated model
  5. heat slider to 2× → recommendation flips to A (top risk, live)
  6. download the offline report
- 🔜 Screenshots and the CLI output as offline backup for the demo
- ⬜ Sensitivity tornado: which assumptions flip the recommendation (the heat factor is the first one)
- ⬜ Animated heat map over time; pack layout drawing with busbars and NTC positions
- ⬜ Persona page: student (learning trade-offs) vs pack engineer (early design screening)

## Phase 5 — Model depth ⬜ (Engineering quality, Innovation 10 %)

- ⬜ Semi-empirical ageing (cycle and calendar, C-rate and temperature) replacing the Arrhenius rule of thumb
- ⬜ Entropic heat; temperature-dependent OCV; hexagonal layout; enclosure air node
- ⬜ Passive-balancing simulation over many cycles
- ⬜ Thermal-propagation screening: one cell at runaway temperature → neighbours vs spacing/barrier (✂️)
- ⬜ Cross-check one design against PyBaMM (✂️)

## Phase 6 — Platform & reuse ⬜ (Business viability 10 %)

- ⬜ Second study (e.g. 5 kWh home ESS) to prove reuse with zero code changes
- ⬜ Design-space sweep → Pareto front (energy vs charge time vs ₹)
- ⬜ In-UI editor for cells, requirements and designs; FastAPI service on the same core
- ⬜ Optional AI "explain this trade-off" panel (✂️, never in the critical path)

## Pitch checklist (map every slide to a criterion)

- [ ] **Problem understanding:**
  - application, operating conditions, requirements table, scope boundary (one 48 V pack)
- [ ] **Desirability:**
  - users: students and pack engineers
  - pain points: siloed data and late discovery of conflicts
  - the hot-climate e-2W safety context
- [ ] **Technical feasibility:** laptop-only, seconds per design, open data, safe low-voltage rig
- [ ] **Engineering quality:**
  - equations and assumptions
  - convergence, heat-balance and hand-calc cross-checks
  - validation RMSE
- [ ] **Prototype & evidence:** live demo, measured vs predicted results, repeatable CLI and report
- [ ] **Innovation:**
  - cause-explaining conflict checker
  - sensor blind-spot detection
  - virtual hotspot sensor
  - variation Monte Carlo
  - evidence-ladder traceability
- [ ] **Business viability:**
  - fewer physical prototypes, conflicts found before hardware
  - ₹/kWh and life comparison
  - zero-BOM firmware fix
- [ ] **Close:** recommendation + stated risks/limitations + next step (LFP charge test; pack-level log)

## Known limitations (state them openly)

- **Data and validation:**
  - NMC: calibrated on a *proxy* cell (LG M50LT, drilled for an internal thermocouple) in a climate chamber,
    single cells — not the cell that would be bought, not a pack. Voltage hold-out 17–18 mV median.
  - Temperature rise under-predicted ~2× on hold-out (no SOC-dependent resistance or entropic heat; chamber
    cooling not separable) — covered by the 2× robustness run, not fixed.
  - LFP cell, costs and masses are generic class values; LFP is **not validated** (top risk).
  - Ageing is a rule of thumb; it is not validated.
  - Model below 10 % SOC: voltage error up to ~0.1–0.9 V near the 2.5 V cut-off (1-RC limit).
- **Model simplifications:**
  - Lumped thermal model with an effective `h`; no CFD and no enclosure air node.
  - The BMS observer in the sim shares the plant's model structure, so real-world error will be larger than
    the ±30 % cooling error we test.
  - One thermal node per cell: the core runs up to 4.6 K above the surface on the proxy cell.
  - The drive profile is synthetic, not a homologation cycle.
- **Scope:** one low-voltage (48 V) pack; no high-voltage system, contactors or insulation monitoring.
- **Regulation:** AIS-156 (Amd. 3, Annex 8K) asks for ≥ 4 temperature sensors placed to read true temperatures;
  the baseline and Option C have 2 — neither is claimed compliant.

## Risks

| Risk | Mitigation |
|---|---|
| Scope creep | Phase 3 + 4 only until the demo is solid; everything else is ✂️-able |
| Model credibility questioned | Proxy-cell calibration with 60-log hold-out; hand-calc bound; heat-balance tests; 2× heat robustness |
| Hardware safety incident | ≤ 2S protected cells, fuse, fireproof bag, supervision, or dataset-only fallback |
| Live demo breaks | CLI output, HTML report and screenshots as backup; all sims cached |
