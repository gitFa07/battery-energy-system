# Issues with the TASK.md approach

`TASK.md` was built in full on branch `AlternatePlanImplementation` (VoltTwin, `src/`). It works and all tests
pass, but building it showed weak spots in the plan itself. This file lists them in plain words, with what to do
about each.

## What is wrong with the plan

### 1. The answers were written before the model
`TASK.md` gives the final results (58.4 °C, 13.8 kg, $310 …) and asks the tests to check that the model hits them.
That is backwards: a model tuned to hit chosen numbers proves nothing, and a judge asking "where does 58.4 °C come
from?" gets no answer.
*What we did:* treated them as targets with a tolerance and listed every gap with its reason.

### 2. It asked us to make up "real" data
Phase 5 says to *synthesize* BatteryArchive data and show it as empirical. That is fake evidence. If anyone found
out, it would cost us the whole evidence score, and more.
*What we did:* used the real TU Berlin lab logs that were already in the repo.

### 3. It never checks the model against reality
Nothing in the plan asks whether the physics is right. When we checked it against the real logs, the cell model
predicted only **¼ to ½ of the real temperature rise**. With just 1.5× more heat, Option B goes over 50 °C and
becomes UNSAFE. So the plan's headline answer ("Option B is optimal") is not reliable yet.

### 4. The physics is too simple for the key question
The whole study is about a pack getting too hot. Yet the plan uses **one temperature for the whole pack**, so it:
- cannot find the hottest cell or show where it sits;
- cannot tell whether the NTC sensors are in the right places. "At least 6 NTCs" is a rule we made up, not a result;
- cannot show what the BMS actually sees compared with the real hotspot.

PackForge already models every cell and what each sensor reads.

### 5. The Round-1 numbers do not add up
- Option A at **$275** is cheaper than the baseline even though it has 54 more cells, a fan and copper busbars.
  Its cells alone cost $193.
- Option A at **43.1 °C** means only a 3 K rise after a ride plus a fast charge, which is not plausible with fan cooling.
- The table misses real problems. At full acceleration the baseline and Option A draw 115 A and 106 A, but their
  fuse and BMS are rated for 100 A. The fuse would blow.

### 6. "Optimal" is partly our own choice
TOPSIS ranks designs with weights we picked (thermal 25 %, charge 20 %, …). Different weights give a different
order, and the plan never tests this. Option B's cost of $356 is also only $4 under the $360 limit, so a small
price change makes it fail.

### 7. It duplicates work we already had
PackForge already solved the same brief, with better physics, calibration and tests. `TASK.md` builds a second
system beside it. This creates two codebases, two sets of results and two currencies ($ vs ₹), and uses
"module" where the project says "pack". Judges see a split, not a stronger product.

### 8. Heavy tools that add little
- **PyBaMM** is a large install and changes no verdict; it is only a cross-check.
- **SQLite** copies JSON files that are already the source.
- **FastAPI** is useful later, but no user needs it for the demo.

### 9. Smaller gaps
- **Few designs, no sensitivity:** the study is fixed at 3 designs. There is no check of cell-to-cell variation or
  ageing, and no sensitivity analysis on the assumptions.
- **LFP is not validated:** the LFP cell has no measured data at all.
- **Bench at the wrong temperature:** the bench test runs at 25 °C lab temperature, not the 40 °C of the study, so it
  measures heat but not hot-climate behaviour.
- **"Fast charge" is ambiguous:** "42 min (derated to 68 min)" leaves unclear which number the requirement means.

## Improvements, most important first

1. **Measure the real heat.** Run the 1S-4P bench test and get the true heat factor, then re-run every design with
   it. Until then, call the recommendation *provisional*.
2. **Fit the cell model to real data.** Use the calibrated PackForge cell (or fit VoltTwin's cell to the TU Berlin
   logs) instead of datasheet values that under-predict heat 2–4×.
3. **Go back to one codebase.** Move the useful VoltTwin parts into PackForge, use one currency (₹) and one set of
   requirement ids, and drop the duplicate stack. The useful parts are the mass/volume/cost checks, the radar, the
   heat-balance chart, the API, the bench protocol and the robustness sweep.
4. **Model every cell, not one lump.** This finds the real hotspot and lets sensor placement be designed rather
   than guessed.
5. **Fix the designs, not just flag them.** Give the baseline and Option A a fuse and BMS rated at least 1.25× the
   peak current, and re-rank.
6. **Fix the target table.** Correct Option A's cost and temperature, and state which charge time REQ-CH-01 means
   (we used the real time, including BMS slow-down).
7. **Test the ranking.** Vary the TOPSIS weights and the key assumptions (cooling, cell cost, heat) and show which
   ones change the winner.
8. **Add variation and ageing.** Add cell-to-cell spread (Monte Carlo) and end-of-life resistance, so the design
   is checked at its worst, not its best.
9. **Validate or flag LFP.** Find a public LFP dataset, or keep marking every LFP result as unvalidated.
10. **Keep the extras optional.** PyBaMM, FastAPI and SQLite stay add-ons; the core should install and run in
    seconds.
