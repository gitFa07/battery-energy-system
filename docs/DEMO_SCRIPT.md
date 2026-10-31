# Demo script: PackForge live demo (about 5 min) and backup clip

This follows the ROADMAP Phase 4 "Live-demo path". Every number here comes from the CLI run
(`docs/backup/cli_output.txt`) or from a replay through the calibrated model. Run the commands from the repo
root with the venv. Terms follow `GLOSSARY.md`: say *pack*, *thermal hold*, *blind spot*, *charge time* (plug-in → 80 %).

## Before the pitch (T − 15 min)

1. `.venv/Scripts/streamlit run app.py` and open `http://localhost:8501` in Chrome, full screen (F11), zoom 90 %.
2. Warm the cache so nothing shows a spinner on stage. Each design/setting is simulated once and then cached:
   - Leave all four designs selected. Visit every tab once.
   - Turn **Charge right after the ride** off, wait for the run, then back on.
   - Move **Unmodelled heat ×** to 2.0, wait for the run, then back to 1.0.
   - Validation tab: pick `TUB_M50LT_AM23NMC00104_CHG-FTP-75_45C.csv` once.
3. Set the starting state: sidebar **Designs** = `baseline` only. Ambient 40 °C. Toggle **on**. Heat × 1.0.
   Tab: **Compare**.
4. Open in other windows, ready to switch to: the backup clip, `docs/backup/packforge_report.html`, and
   `docs/backup/cli_output.txt`. Keep the deck downloaded as a PDF (the web deck needs internet for its fonts).

## The demo

| Time | Step | Click | Say | You should see |
|---|---|---|---|---|
| 0:00 | **1 · Baseline after a ride** | (start state) | "Our baseline: a 13S10P NMC pack, two NTCs on the edge, 40 °C, plugged in right after the ride." | Red banner: *No design meets every must requirement*. Compare: charge time **243.7 min**, thermal hold **48.2 min**, peak cell temp (charge) **47.6 °C ❌** |
| 0:30 | 1 · cold vs hot | Toggle **Charge right after the ride** off, then on again | "Plug in from ambient and it passes: 44.7 °C, 136 min. The hot plug-in is what breaks it." | Off: no red banner, peak charge temp 44.7 °C. On: back to 47.6 °C ❌ |
| 0:50 | 1 · where the heat is | **Heat map** tab | "At the end of the ride the interior cells are hottest, about 53 °C. The rings are the two BMS sensors, in the corners. They read cooler cells." | Ride-peak map: hot interior, ◯ rings on two corner cells |
| 1:10 | 1 · what the BMS sees | **Time series** tab, Scenario **charge** (default signals), scroll down | "Top: the hottest cell. Bottom: what the BMS acts on, more than a kelvin lower all the way. It waits 48 min, then charges while the hottest cell is at 47.6 °C. No alarm, no trip." | Two charts (Max cell temp, BMS hotspot view); caption *t=48.2 min: charging released after thermal hold* |
| 1:30 | **2 · Option C** | Sidebar **Designs**: add `option_c_smartcharge`. **Compare** tab | "Option C changes only BMS settings: it derates on a thermal observer, a virtual hotspot sensor. It passes: 44.5 °C. But it is slower, 277 min, because it honestly waits for the hotspot." | C: peak 44.5 °C, hold 89.5 min, charge time 276.6 min. Banner: C recommended + retrofit |
| 2:00 | 2 · why baseline fails | **Conflicts** tab | "Every failure comes with its cause chain across subsystems and candidate fixes." | Baseline REQ-03 expander open: cause chain + fixes |
| 2:20 | **3 · Compare A and B** | **Designs**: add `option_a_fastcharge` and `option_b_lfp`. **Compare** tab | "A adds an aluminium plate: 92 min. B switches to LFP: 97 min, cheapest per kWh, about 3× the life, but 22.7 kg." | Three banners: **Recommended: Option B**; *If pack mass and pack volume are hard limits: Option A*; *Retrofit for packs already built: Option C*. Ranking B, A, C, baseline ❌ |
| 2:50 | **4 · Validation** | **Validation** tab. Point at the metric tiles, then pick `TUB_M50LT_AM23NMC00104_CHG-FTP-75_45C.csv` in **Replay a log** | "Calibrated on a public proxy cell at 25 and 35 °C. This is a 45 °C charge the fit never saw: 17 mV voltage error. Temperature: we under-predict the rise about 2×, and we say so." | Tiles: drives 18 mV, charges 17 mV (n = 30 each). Caption: **Hold-out — not used in the fit.** V RMSE 17 mV (SOC ≥ 10 %), 22 mV (all), T RMSE 0.49 K, core up to 3.6 K above surface |
| 3:30 | **5 · Top risk, live** | Sidebar **Unmodelled heat ×** → **2.0** | "Our pick uses an LFP cell we have not validated. If cells make twice the modelled heat, B misses the charge limit by 0.02 K and the tool switches to A. One LFP charge test settles it." | Caption: *cells generate 2× the modelled heat*. Banner: **Recommended: Option A** |
| 4:00 | reset | **Unmodelled heat ×** → **1.0** | — | Banner back to Option B |
| 4:10 | **6 · Report** | **⬇️ Download design report (HTML)**, open the file | "Everything we showed, in one offline HTML file: KPIs, conflicts, recommendation, the 2× heat run, validation." | Report opens in the browser with no network |
| 4:40 | end | Back to the deck | "Build B, keep A ready, ship C today." | — |

UI behaviour to expect (seen in the rehearsal recording):
- Adding a design: click in **Designs**, type part of its name (`option_c`), press Enter, then Esc. Wait for
  the rerun before typing the next one, or the keystrokes land late.
- Every rerun (design added, toggle, slider) jumps back to the **Compare** tab, and the **Replay a log** box
  resets to the first log. Re-pick `…CHG-FTP-75_45C.csv` if you come back to Validation.
- The browser can freeze for a few seconds after a rerun while it redraws the charts. Keep talking.
- Click on the heat slider track to jump straight to a value; 2.0 sits two-thirds of the way along.

The report captures whatever is on screen. Set the heat slider back to 1.0 and keep all four designs selected
before you download it.

Optional, only if there is time or a judge asks: **Traceability** (pick Baseline: requirement → metric →
assumption with evidence levels) and **Monte Carlo** (Baseline, 50 packs, **Run Monte Carlo**; runs live, so
warm it before the pitch if you plan to show it).

## Fallbacks

| Problem | Do this |
|---|---|
| Spinner longer than ~10 s | Keep talking. At 20 s switch to the backup clip at the same step. |
| App errors or the browser tab dies | Play the backup clip from that step. In the background run `.venv/Scripts/streamlit run app.py` again. |
| Laptop or projector failure | Use the deck PDF: slides 3, 9, 10, 11 hold every demo number. |
| Clip will not play | Open `docs/backup/packforge_report.html` (offline) and `docs/backup/cli_output.txt`. |
| A judge asks for a setting we have not cached | Say it takes a few seconds per design, run it, keep talking about what you expect to see. |

## Likely questions (short answers)

- **Is the NMC data your cell?** No. It is a proxy cell (LG M50LT, TU Berlin, CC BY 4.0), fitted at 25/35 °C
  and checked on 60 logs at 45 °C. We call it "measured (proxy)".
- **Is LFP validated?** No. That is our top risk. At 2× heat B fails by 0.02 K and A becomes the pick.
- **Is any design AIS-156 compliant?** We do not claim it. The baseline and C have 2 sensors, and Amd. 3,
  Annex 8K asks for at least 4.
- **Why is C slower than the baseline?** It waits until the observer's hotspot is in the derate window: 90 min
  hold instead of 48. Being slower is what makes it safe.
- **How do you know the sim is right?** Heat balance ±2 %, energy 0.9–1.06× nominal, 2 s vs 1 s step within
  0.4 %, a hand-calc bound, the hold-out check, and 23 tests.

---

# Backup clip: shot list

Goal: a 3–4 min screen recording of the same path, which you can play from any step if the live demo fails.
Record at 1920×1080 with OBS (or Win + Alt + R with Xbox Game Bar for the browser only). Do the
"Before the pitch" steps first so no spinner appears. Hide the bookmarks bar and notifications. Record without
sound and talk over it live, or add one subtitle per shot (the subtitle column).

| # | Length | Setup → action | On screen | Subtitle |
|---|---|---|---|---|
| 1 | 15 s | Start state (baseline only, 40 °C, toggle on). Hold on **Compare** | Red banner; 243.7 min; 48.2 min hold; 47.6 °C ❌ | Baseline after a ride: 48 min hold, then charging at 47.6 °C |
| 2 | 15 s | Toggle **Charge right after the ride** off → hold 5 s → on | 44.7 °C passes → 47.6 °C ❌ | From ambient it passes. The hot plug-in breaks it |
| 3 | 15 s | **Heat map** tab, hover the hottest cell | Interior hotspot, edge sensor rings | The BMS sensors sit where the pack is coolest: 3.2 K blind spot |
| 4 | 15 s | **Time series**, charge | Max cell vs BMS view, with a gap | What the BMS sees vs the hottest cell |
| 5 | 20 s | Add `option_c_smartcharge`; **Compare**, then **Conflicts** | C 44.5 °C, 276.6 min; REQ-03 cause chain | Option C: ₹0 firmware fix. Safe, but slower |
| 6 | 20 s | Add `option_a_fastcharge`, `option_b_lfp`; **Compare**, scroll to the radar and ranking | Three banners; ranking B, A, C | Three answers: B recommended, A if mass is limited, C for packs already built |
| 7 | 25 s | **Validation**: tiles, then replay `TUB_M50LT_AM23NMC00104_CHG-FTP-75_45C.csv` | Hold-out caption, voltage and temperature plots | 45 °C hold-out charge, never used in the fit: 17 mV |
| 8 | 15 s | **Unmodelled heat ×** 1.0 → 2.0 | Banner flips to Option A | Top risk: at 2× heat, A becomes the pick |
| 9 | 10 s | Heat back to 1.0; **⬇️ Download design report (HTML)**; open it | Report title, scroll through KPIs and recommendation | One offline report |
| 10 | 20 s | Terminal: `.venv/Scripts/python -m packforge --report docs/backup/packforge_report.html` (run takes ~30 s: cut or speed it up 2×) | KPI table, conflicts, ranking, three recommendations, 2× heat block | Same results from the command line |

After recording, also save screenshots of shots 1, 3, 6, 7 and 8 as stills (PNG). They are the last-resort
backup and can go into the deck if a slide needs a real UI image.

Already generated (2026-10-31), in `docs/backup/`. Regenerate them after any model or study change:
- `cli_output.txt` and `packforge_report.html` (6 MB, offline).
- Three silent GIFs recorded with Chrome automation. They have click markers and action labels but no
  subtitles. They are a stopgap until the full clip is recorded:
  - `packforge_demo_1_baseline_problem.gif` covers shots 1–4: baseline, cold vs hot, heat map, time series.
  - `packforge_demo_2_options_recommendation.gif` covers shots 5–6: C, conflicts, then A and B with the ranking.
  - `packforge_demo_3_validation_robustness.gif` covers shots 7–9: hold-out replay, the 2× heat flip to A,
    reset. It ends hovering the report button; the download itself is not shown.
