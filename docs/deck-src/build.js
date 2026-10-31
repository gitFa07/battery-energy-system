// PackForge pitch deck, academic structured-argument redesign (pptxgenjs).
// Numbers: CLI run of studies/escooter_48v + calibration record (unchanged from the previous deck).
const pptxgen = require("pptxgenjs");

const OUT = process.argv[2] || "PackForge_pitch.pptx";

// Three colours: navy primary, blue accent (focus), orange alert (hot / fail). Greys are neutral.
const C = {
  navy: "1F4E79", blue: "2E75B6", alert: "C2410C",
  blueTint: "DEEAF6", alertTint: "FBE3D6", panel: "F2F4F7",
  text: "262626", muted: "6B7280", line: "D0D5DB", grey: "A6ADB4", white: "FFFFFF",
};
const F = "Calibri";
const W = 13.333, X0 = 0.6, CW = W - 2 * X0;
const SECTIONS = ["Problem", "Approach", "Evidence", "Results", "Demo", "Impact"];

// Keep numbers with their units and IDs whole: no line break inside "80 %", "≤ 45 °C", "REQ-03".
const nb = (t) => t
  .replace(/(\d) (?=%|°C|K\b|min\b|mV\b|Wh\b|kg\b|L\b|Ah\b|Ω|s\b|k\b|V\b|cycles\b|→)/g, "$1 ")
  .replace(/(≤|≥|~|±|→|₹) /g, "$1 ")
  .replace(/\b(REQ|AIS)-(\d)/g, "$1‑$2");
const nbAll = (t) => typeof t === "string" ? nb(t)
  : Array.isArray(t) ? t.map(r => (r && typeof r.text === "string") ? { ...r, text: nb(r.text) } : r) : t;

const run = (text, o = {}) => ({ text, options: o });
const bullets = (items, o = {}) => items.map((t, i) => run(t, { bullet: true, ...o,
  ...(i < items.length - 1 ? { breakLine: true } : {}) }));

function breadcrumb(s, section, tag) {
  const runs = [];
  if (SECTIONS.includes(section)) {
    SECTIONS.forEach((name, i) => {
      runs.push(run(name, { bold: name === section, color: name === section ? C.navy : C.muted }));
      if (i < SECTIONS.length - 1) runs.push(run("   ·   ", { color: C.line }));
    });
  } else runs.push(run(section, { bold: true, color: C.navy }));
  s.addText(runs, { x: X0, y: 0.3, w: 8.5, h: 0.3, margin: 0, fontFace: F, fontSize: 12 });
  if (tag) s.addText(tag, { x: W - X0 - 4, y: 0.3, w: 4, h: 0.3, margin: 0, fontFace: F, fontSize: 12,
    color: C.muted, align: "right" });
}

function frame(s, n, { section, tag, title, source }) {
  breadcrumb(s, section, tag);
  s.addText(title, { x: X0, y: 0.68, w: CW, h: 1.0, margin: 0, fontFace: F, fontSize: 26, bold: true,
    color: C.navy, valign: "top" });
  if (source) s.addText(source, { x: X0, y: 6.95, w: 11, h: 0.3, margin: 0, fontFace: F, fontSize: 12,
    color: C.muted });
  s.addText(String(n), { x: W - X0 - 0.8, y: 6.95, w: 0.8, h: 0.3, margin: 0, fontFace: F, fontSize: 12,
    color: C.muted, align: "right" });
}

function bodyText(s, items, x, y, w, h, o = {}) {
  s.addText(bullets(items), { x, y, w, h, margin: 0, fontFace: F, fontSize: 20, color: C.text, valign: "top",
    paraSpaceAfter: 14, ...o });
}

function caption(s, text, x, y, w, h = 0.4, o = {}) {
  s.addText(text, { x, y, w, h, margin: 0, fontFace: F, fontSize: 16, color: C.muted, valign: "top", ...o });
}

function box(s, x, y, w, h, fill) {
  s.addShape("rect", { x, y, w, h, fill: { color: fill }, line: { color: fill } });
}

function lerp(a, b, t) {
  const pa = [0, 2, 4].map(i => parseInt(a.substr(i, 2), 16));
  const pb = [0, 2, 4].map(i => parseInt(b.substr(i, 2), 16));
  return pa.map((v, i) => Math.round(v + (pb[i] - v) * t).toString(16).padStart(2, "0")).join("").toUpperCase();
}

// Common table styling; header row navy, body 18 pt (16 pt in the appendix).
const th = (t, o = {}) => ({ text: t, options: { bold: true, color: C.white, fill: { color: C.navy }, ...o } });
const td = (t, o = {}) => ({ text: t, options: o });
const tableOpts = (o) => ({ fontFace: F, fontSize: 18, color: C.text, valign: "middle",
  margin: [0.04, 0.1, 0.04, 0.1], border: { type: "solid", pt: 0.75, color: C.line }, ...o });

const chartBase = {
  catAxisLabelColor: C.text, catAxisLabelFontSize: 16, catAxisLabelFontFace: F,
  valAxisLabelColor: C.muted, valAxisLabelFontSize: 14, valAxisLabelFontFace: F,
  valGridLine: { color: "E5E7EB", size: 0.5 }, catGridLine: { style: "none" },
  dataLabelFontFace: F, dataLabelFontSize: 16, titleFontFace: F, titleFontSize: 16, titleColor: C.text,
  legendFontFace: F, legendFontSize: 16,
};

async function main() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE";
  pres.title = "PackForge: pitch";
  pres.author = "Falak Anwar, Zaid Alam";
  let n = 0;
  const slide = (bg = C.white) => {
    const s = pres.addSlide(); s.background = { color: bg }; n++;
    const addText = s.addText.bind(s), addTable = s.addTable.bind(s);
    s.addText = (t, o) => addText(nbAll(t), o);
    s.addTable = (rows, o) => addTable(rows.map(r => nbAll(r)), o);
    return s;
  };

  // 1 · Title
  {
    const s = slide(C.navy);
    s.addText("PackForge finds the hot-charge failure in a battery pack before the hardware does", {
      x: X0, y: 1.7, w: 10.5, h: 2.0, margin: 0, fontFace: F, fontSize: 40, bold: true, color: C.white,
      valign: "top" });
    s.addText("A reusable design workbench for battery packs, shown on one 48 V e-scooter study", {
      x: X0, y: 3.85, w: 10.5, h: 0.5, margin: 0, fontFace: F, fontSize: 22, color: C.blueTint });
    s.addText([
      run("Falak Anwar · Zaid Alam", { bold: true, fontSize: 20, color: C.white, breakLine: true }),
      run("TELIPORT Season 4 · Tata Elxsi · Case Study 2: Reusable Digital Platform for Designing Battery Energy Systems",
        { fontSize: 16, color: C.blueTint, breakLine: true }),
      run("Day 3 pitch · 2026", { fontSize: 16, color: C.blueTint }),
    ], { x: X0, y: 5.25, w: 11.5, h: 1.2, margin: 0, fontFace: F, valign: "top", paraSpaceAfter: 4 });
    s.addNotes("Open with the question every e-scooter owner faces in an Indian summer: can I charge right after the ride? PackForge answers it for any pack design before hardware is built. Today we show one study: a 48 V scooter pack, four designs, one hard day.");
  }

  // 2 · Situation: the operating case
  {
    const s = slide();
    frame(s, n, { section: "Problem", tag: "Problem understanding",
      title: "A 48 V scooter pack plugged in straight after a 40 °C ride is the hardest realistic charging case",
      source: "Requirements: studies/escooter_48v/study.json (all 11 in Appendix A1). Scope: one low-voltage pack." });
    const stages = [
      ["1 · Ride", "Urban cycle at 40 °C ambient. Baseline: 13S10P NMC 21700, 2,263 Wh usable."],
      ["2 · Plug in", "Charging starts from the end-of-ride state, with the pack still hot."],
      ["3 · Charge to 80 %", "CC-CV. The BMS derates on what its two sensors read."],
    ];
    const limits = [
      ["Cells ≤ 55 °C while riding (REQ-04)", false],
      ["Blind spot ≤ 3 K: hottest cell minus what the BMS sees (REQ-07)", true],
      ["Cells ≤ 45 °C while charging (REQ-03, must) · plug-in → 80 % ≤ 120 min (REQ-05)", true],
    ];
    const bw = 3.6, gap = (CW - 3 * bw) / 2;
    stages.forEach(([t, b], i) => {
      const x = X0 + i * (bw + gap);
      box(s, x, 1.95, bw, 2.15, C.panel);
      s.addText([run(t, { bold: true, fontSize: 20, color: C.navy, breakLine: true }), run(b, { fontSize: 18 })],
        { x: x + 0.25, y: 2.1, w: bw - 0.5, h: 1.85, margin: 0, fontFace: F, color: C.text, valign: "top",
          paraSpaceAfter: 6 });
      if (i < 2) s.addShape("rightArrow", { x: x + bw + gap / 2 - 0.17, y: 2.85, w: 0.34, h: 0.36,
        fill: { color: C.grey }, line: { color: C.grey } });
      const [lt, hot] = limits[i];
      box(s, x, 4.75, bw, 1.65, hot ? C.alertTint : C.panel);
      s.addText(lt, { x: x + 0.25, y: 4.85, w: bw - 0.5, h: 1.45, margin: 0, fontFace: F, fontSize: 18,
        color: hot ? C.alert : C.text, bold: hot, valign: "middle" });
    });
    caption(s, "Limit at each stage. Orange: where the baseline gets into trouble.", X0, 4.3, CW);
    s.addNotes("The study is one 48 V e-scooter pack on the hardest realistic day: 40 °C ambient, plugged in straight after the ride, so the charge starts from the pack's end-of-ride state. Must-requirements disqualify a design; should-requirements become stated risks. The orange limits are where the baseline gets into trouble. Charge time runs from plug-in to 80 %, including any thermal hold, because that is what the rider waits for. All 11 requirements are in Appendix A1.");
  }

  // 3 · Research question
  {
    const s = slide();
    frame(s, n, { section: "Problem", tag: "Problem understanding · Desirability",
      title: "Our question: which pack design charges at ≤ 45 °C and reaches 80 % within 120 min after a hot ride, and how sure can we be before building it?" });
    const cols = [
      ["Who needs the answer", ["Students and new engineers: why a design fails", "Pack engineers: which option to prototype"]],
      ["What counts as an answer", ["A ranked design that meets every must-requirement", "A cause and candidate fixes for every failure", "An evidence level on every number"]],
    ];
    cols.forEach(([h, items], i) => {
      const x = i ? 6.87 : X0, w = 5.86;
      box(s, x, 2.3, w, 3.9, i ? C.blueTint : C.panel);
      s.addText(h, { x: x + 0.35, y: 2.55, w: w - 0.7, h: 0.45, margin: 0, fontFace: F, fontSize: 22, bold: true,
        color: C.navy });
      bodyText(s, items, x + 0.35, 3.25, w - 0.7, 2.8);
    });
    s.addNotes("We set out to answer one question: which design charges at or below 45 °C and reaches 80 % within two hours when plugged in after a hot ride, and how far can we trust that answer before anyone builds the pack? Two groups need it. Students and new engineers want to see why a design fails. Pack engineers have to decide which option to prototype. An answer counts only if it comes with a cause for every failure and an evidence level for every number.");
  }

  // 4 · Complication: the blind spot
  {
    const s = slide();
    frame(s, n, { section: "Problem", tag: "Problem understanding",
      title: "The baseline BMS reads its hottest cell 3.2 K low, so it charges interior cells at 47.6 °C",
      source: "Source: PackForge CLI, baseline, charge right after the drive at 40 °C ambient (docs/backup/cli_output.txt)" });
    const cols = 13, rows = 10, pitch = 0.4, gx = X0 + 0.1, gy = 1.95, d = pitch * 0.82;
    const cx = (cols - 1) / 2, cy = (rows - 1) / 2, rmax = Math.hypot(cx, cy);
    const stops = ["BDD7EE", "F4B183", C.alert];
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      const t = 1 - Math.hypot(c - cx, (r - cy) * 1.15) / rmax;
      const col = t < 0.5 ? lerp(stops[0], stops[1], Math.max(0, t) / 0.5) : lerp(stops[1], stops[2], (t - 0.5) / 0.5);
      s.addShape("ellipse", { x: gx + c * pitch, y: gy + r * pitch, w: d, h: d, fill: { color: col }, line: { color: col } });
    }
    for (const [c, r] of [[0, 0], [cols - 1, rows - 1]]) {
      const e = 0.07;
      s.addShape("ellipse", { x: gx + c * pitch - e, y: gy + r * pitch - e, w: d + 2 * e, h: d + 2 * e,
        fill: { type: "none" }, line: { color: C.navy, width: 2.5 } });
    }
    s.addShape("ellipse", { x: gx + 4.6 * pitch, y: gy + 3.5 * pitch, w: 3.8 * pitch, h: 2.8 * pitch,
      fill: { type: "none" }, line: { color: C.navy, width: 2, dashType: "dash" } });
    const lx = gx, ly = gy + rows * pitch + 0.15;
    s.addShape("ellipse", { x: lx, y: ly + 0.07, w: 0.26, h: 0.26, fill: { type: "none" }, line: { color: C.navy, width: 2.5 } });
    caption(s, "NTC sensor (2, on corners)", lx + 0.4, ly, 2.7, 0.4, { color: C.text, valign: "middle" });
    s.addShape("ellipse", { x: lx + 3.25, y: ly + 0.07, w: 0.36, h: 0.26, fill: { type: "none" }, line: { color: C.navy, width: 2, dashType: "dash" } });
    caption(s, "Hottest interior cells", lx + 3.75, ly, 2.4, 0.4, { color: C.text, valign: "middle" });
    caption(s, "Illustrative layout: blue cooler, orange hotter. Simulated field: app, Heat map tab.", lx, ly + 0.45, 6.2, 0.35, { fontSize: 12 });
    bodyText(s, [
      "Edge NTCs cool first and read 3.2 K below the hottest cell (limit 3 K)",
      "The BMS holds charging for 48 min until its sensors cool",
      "Then interior cells charge at 47.6 °C, above the 45 °C limit",
      "Nothing on the BMS shows it",
    ], 7.35, 2.05, 5.38, 4.6);
    s.addNotes("After the ride the cells next to the sensors cool first, so the two NTCs read 3.2 K below the hottest cell. The BMS waits 48 minutes with no current, then charges and derates on what the NTCs report. Meanwhile interior cells reach 47.6 °C, above the 45 °C charge limit. There is no alarm and no trip, because the BMS cannot see those cells. All three numbers come from the CLI run of the baseline. The drawing is illustrative; the simulated heat map is in the app.");
  }

  // 5 · Complication: the physics floor (skip if short)
  {
    const s = slide();
    frame(s, n, { section: "Problem", tag: "Engineering quality · skip if short",
      title: "At 40 °C ambient a passive NMC pack needs at least 139 min to charge 10 → 80 %, whatever the firmware does",
      source: "Source: PackForge CLI, thermal-limit charge bound (hand calc) vs simulated 10–80 % charge, baseline" });
    const cats = ["Hand-calc bound (cold start)", "Simulated (after a ride)"];
    s.addChart(pres.charts.BAR, [
      { name: "Bound", labels: cats, values: [139, 0] },
      { name: "Simulated", labels: cats, values: [0, 161] },
    ], { ...chartBase, x: X0, y: 1.9, w: 6.4, h: 4.2, barDir: "col", barGrouping: "stacked", barGapWidthPct: 60,
      chartColors: [C.alert, C.grey], showValue: true, dataLabelPosition: "inEnd", dataLabelFormatCode: '0" min";;',
      dataLabelColor: C.white, dataLabelFontBold: true, showLegend: false,
      showTitle: true, title: "Charge time 10 → 80 %, passive NMC pack (min)", valAxisMinVal: 0, valAxisMaxVal: 180 });
    caption(s, "A test keeps the cold-start simulation within 0.95–1.3× of this bound.", X0, 6.2, 6.4, 0.6);
    bodyText(s, [
      "40 °C ambient leaves 5 K below the 45 °C limit for all the charge heat",
      "Bound: full current to the limit, then the current that holds it there",
      "Charging faster needs hardware: better cooling (A) or a cooler-running cell (B)",
      "Firmware (C) can make charging safe, not faster",
    ], 7.35, 2.05, 5.38, 4.6);
    s.addNotes("At 40 °C ambient the 45 °C limit leaves 5 K for all the charge heat. An independent hand calculation takes the ideal profile for an interior cell: full current until it reaches the limit, then exactly the current that holds it there. It says a passive NMC pack needs at least 139 minutes for 10 to 80 %, even from a cold start. The simulation gives 161 minutes after a ride, and a test keeps the cold-start simulation within 0.95 to 1.3 times the bound. Firmware cannot beat this floor; only moving heat out or making less of it can. If time is short, skip this slide and say one line: the fix is hardware.");
  }

  // 6 · Approach: one design file
  {
    const s = slide();
    frame(s, n, { section: "Approach", tag: "Innovation · Technical feasibility",
      title: "One design file feeds the simulator, the conflict checker and the ranking, so every option is tested the same way",
      source: "PackForge: packforge/ Python package; Streamlit UI, CLI and HTML report share one core. Details: Appendix A6." });
    const steps = [
      ["Design file", "Cell, S×P layout, cooling, sensors, BMS. Options hold only their diffs.", "One source of truth, no copied parameters"],
      ["Sim + BMS", "1-RC cell, one thermal node per cell. The BMS sees only its sensors.", "Virtual hotspot sensor; blind-spot metric"],
      ["KPIs", "Charge time, peak temperature, blind spot, mass, cost, life.", "Evidence level on every number; Monte Carlo spread"],
      ["Conflict checker", "11 requirements and 14 interface rules.", "Cause chain and fixes for each failure"],
      ["Rank and report", "Ranking, traceability, offline HTML report.", "Three answers; 2× heat re-run"],
    ];
    const gap = 0.32, bw = (CW - 4 * gap) / 5;
    steps.forEach(([t, b, inv], i) => {
      const x = X0 + i * (bw + gap);
      box(s, x, 1.95, bw, 2.45, C.panel);
      s.addText([run(`${i + 1} · ${t}`, { bold: true, fontSize: 18, color: C.navy, breakLine: true }),
        run(b, { fontSize: 16 })], { x: x + 0.18, y: 2.08, w: bw - 0.36, h: 2.2, margin: 0, fontFace: F,
        color: C.text, valign: "top", paraSpaceAfter: 6 });
      if (i < 4) s.addShape("rightArrow", { x: x + bw + gap / 2 - 0.12, y: 3.0, w: 0.24, h: 0.3,
        fill: { color: C.grey }, line: { color: C.grey } });
      box(s, x, 5.0, bw, 1.55, C.blueTint);
      s.addText(inv, { x: x + 0.18, y: 5.08, w: bw - 0.36, h: 1.4, margin: 0, fontFace: F, fontSize: 16,
        bold: true, color: C.navy, valign: "middle" });
    });
    s.addText("New in PackForge", { x: X0, y: 4.55, w: 4, h: 0.38, margin: 0, fontFace: F, fontSize: 16, bold: true,
      color: C.blue });
    s.addNotes("One design file is the single source of truth. Each option is a small JSON file that extends the baseline with only its differences. The simulator runs the ride, then the charge from the ride's end state, with a BMS that only knows what its sensors tell it. Every KPI carries an evidence level, and the conflict checker turns each failure into a cause chain with fixes. The blue row is what a spreadsheet or a single-physics tool does not give you: the virtual hotspot sensor, the blind-spot metric, evidence levels, Monte Carlo and cause chains. A new cell, study or rule is a data file, not code.");
  }

  // 7 · Evidence: hold-out validation
  {
    const s = slide();
    frame(s, n, { section: "Evidence", tag: "Prototype & evidence · Engineering quality",
      title: "On 60 unseen 45 °C logs the model predicts voltage within 18 mV but underestimates heating about 2×",
      source: "Data: Yao, Droese & Kowal (2026), TU Berlin, DOI 10.14279/depositonce-25110, CC BY 4.0. Full table: Appendix A2." });
    const cats = ["Drive cycles (30 logs)", "1C charges (30 logs)"];
    s.addChart(pres.charts.BAR, [
      { name: "Measured", labels: cats, values: [2.0, 3.4] },
      { name: "Model", labels: cats, values: [1.0, 1.6] },
    ], { ...chartBase, x: X0, y: 1.9, w: 6.4, h: 4.6, barDir: "col", barGrouping: "clustered", barGapWidthPct: 70,
      chartColors: [C.alert, C.navy], showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0.0" K"',
      dataLabelColor: C.text, showLegend: true, legendPos: "b", showTitle: true,
      title: "Temperature rise on 45 °C hold-out logs (K)", valAxisMinVal: 0, valAxisMaxVal: 4 });
    s.addText("Model ≈ half the measured rise", { x: 1.5, y: 2.6, w: 2.8, h: 0.7, margin: 0, fontFace: F,
      fontSize: 16, bold: true, color: C.alert, valign: "top" });
    bodyText(s, [
      "Fitted at 25 and 35 °C on a proxy cell (LG M50LT, public TU Berlin data)",
      "Hold-out: 60 logs at 45 °C, never used in the fit",
      "Voltage RMSE at SOC ≥ 10 %: 18 mV drives, 17 mV charges (median)",
      "The model gives about half the measured rise, so every design is re-run at 2× heat",
    ], 7.35, 2.05, 5.38, 4.6);
    s.addNotes("The NMC cell is calibrated on a proxy cell, the LG M50LT from the public TU Berlin internal-temperature dataset, not the cell we would buy. We fit at 25 and 35 °C and held out everything at 45 °C: 60 logs the fit never saw. Voltage error is 17 to 18 mV median in the operating window, so the model's heat generation holds at an unseen temperature. The chart shows the weak point: the model predicts about half the measured temperature rise. It has no SOC-dependent resistance or entropic heat. That is why every design is re-run with twice the heat. The chamber's cooling is a test-rig parameter and is never carried over to a pack.");
  }

  // 8 · Results: charge time
  {
    const s = slide();
    frame(s, n, { section: "Results", tag: "Prototype & evidence",
      title: "Options A and B charge to 80 % in under 100 min after a hot ride; the baseline is disqualified at 47.6 °C",
      source: "Source: python -m packforge studies/escooter_48v, calibrated NMC cell. All KPIs: Appendix A3." });
    const cats = ["Baseline · 244 min", "A: NMC + Al plate · 92 min", "B: LFP 16S8P · 97 min", "C: + observer · 277 min"];
    s.addChart(pres.charts.BAR, [
      { name: "Thermal hold (no current)", labels: cats, values: [48.2, 0, 0, 89.5] },
      { name: "Charging", labels: cats, values: [195.5, 92.1, 97.4, 187.1] },
    ], { ...chartBase, x: X0, y: 1.9, w: 6.6, h: 4.75, barDir: "bar", barGrouping: "stacked", barGapWidthPct: 50,
      catAxisOrientation: "maxMin", chartColors: [C.alert, C.navy], showValue: true, dataLabelPosition: "ctr",
      dataLabelFormatCode: "0;;", dataLabelColor: C.white, dataLabelFontBold: true, showLegend: true, legendPos: "b",
      showTitle: true, title: "Plug-in → 80 % (min)", valAxisMinVal: 0, valAxisMaxVal: 300,
      valAxisMajorUnit: 60 });
    // REQ-05 limit drawn over the plot at 120 min (plot x: 0 min at 3.267", 300 min at 6.892", from the render).
    const x120 = 3.267 + (120 / 300) * (6.892 - 3.267);
    s.addShape("line", { x: x120, y: 2.72, w: 0, h: 3.32, line: { color: C.alert, width: 2, dashType: "dash" } });
    s.addText("120 min limit (REQ-05)", { x: x120 + 0.1, y: 3.8, w: 2.1, h: 0.4, margin: 0, fontFace: F, fontSize: 14,
      bold: true, color: C.alert, valign: "middle" });
    bodyText(s, [
      "Baseline holds 48 min, then charges at 47.6 °C and is disqualified",
      "A (Al conduction plate): 92 min. B (LFP): 97 min. Both meet the 120 min limit",
      "C (BMS change only) stays at 44.5 °C but is the slowest, at 277 min",
    ], 7.55, 2.05, 5.18, 4.6);
    s.addNotes("Same study, same scenarios, four designs. Orange is the thermal hold: plugged in, no current. The baseline is disqualified because it charges at 47.6 °C. A adds an aluminium conduction plate and six centre NTCs. B switches to LFP. C keeps the baseline hardware and changes only the BMS, which now derates on a thermal observer, a virtual hotspot sensor. C is safe but slowest because it waits for the hotspot to cool. Calibrating the NMC cell changed the numbers (the hold went from 7 to 48 minutes) but not the ranking.");
  }

  // 9 · Results: three answers
  {
    const s = slide();
    frame(s, n, { section: "Results", tag: "Prototype & evidence · Business viability",
      title: "We recommend B for new packs, A where mass and volume are capped, and C as a ₹0 retrofit",
      source: "Source: recommend() in packforge/engine.py, printed by the CLI. Costs and masses are generic class values." });
    const bcol = { fill: { color: C.blueTint } };
    const L = (t) => td(t, { bold: true, color: C.navy });
    const rows = [
      [th(""), th("B · LFP 16S8P (recommended)"), th("A · NMC + Al plate"), th("C · baseline + observer")],
      [L("Use for"), td("New packs", bcol), td("Mass and volume capped"), td("2-NTC packs already built")],
      [L("Plug-in → 80 %"), td("97 min", { ...bcol, bold: true }), td("92 min", { bold: true }), td("277 min", { bold: true })],
      [L("Cost"), td("₹18.2 k per usable kWh, the lowest", bcol), td("+₹2.7 k per pack"), td("₹0: BMS settings only")],
      [L("Risk"), td("Over the mass (22.7 kg) and volume (13.1 L) targets; LFP cell not validated", bcol),
        td("+1.2 kg; the only design that passes at 2× heat"), td("Slower; 2 sensors, so not AIS-156 compliant (≥ 4)")],
    ];
    s.addTable(rows, tableOpts({ x: X0, y: 1.95, w: CW, colW: [2.2, 3.311, 3.311, 3.311], rowH: [0.55, 0.7, 0.7, 0.9, 1.25] }));
    s.addNotes("The tool gives three answers, one per situation. B is recommended: the lowest cost per kWh, about three times the cycle life by our estimate, 97 minutes, but about 10 kg heavier and bulkier. If mass and volume are hard limits, A: plus ₹2.7 k and 1.2 kg per pack, 92 minutes, and the most robust to extra heat. For the 2-NTC packs already on the road, C is a ₹0 firmware retrofit. It stops hot charging but takes 277 minutes against the baseline's 244, because it waits for the hotspot. We do not claim AIS-156 compliance for any design: the baseline and C have 2 sensors, and Amendment 3, Annex 8K asks for at least 4.");
  }

  // 10 · Discussion: top risk
  {
    const s = slide();
    frame(s, n, { section: "Results", tag: "Engineering quality",
      title: "If cells make 2× the modelled heat, B misses the charge limit by 0.02 K and A becomes the pick",
      source: "Source: CLI robustness re-run; cells generate 2× the modelled heat and the BMS is not told. Charge time: plug-in → 80 %." });
    const hi = { fill: { color: C.blueTint }, bold: true };
    const bad = { color: C.alert };
    const rows = [
      [th("Design"), th("Charge time"), th("Result at 2× heat")],
      [td("Baseline"), td("339 min"), td("Fails REQ-03 and REQ-04 (64 °C riding)", bad)],
      [td("A · NMC + Al plate", hi), td("132 min", hi), td("Passes: charge peak 45.0 °C", hi)],
      [td("B · LFP 16S8P"), td("173 min"), td("Fails REQ-03 by 0.02 K", { ...bad, bold: true })],
      [td("C · baseline + observer"), td("392 min"), td("Fails REQ-04 (64 °C riding)", bad)],
    ];
    s.addTable(rows, tableOpts({ x: X0, y: 1.95, w: 6.7, colW: [2.35, 1.65, 2.7], rowH: [0.55, 0.85, 0.85, 0.85, 0.85] }));
    bodyText(s, [
      "Why 2×: on the 45 °C hold-out logs, cells heat about twice as much as the model",
      "B rests on an LFP cell with generic class values, not validated",
      "One LFP charge test through the same fit pipeline decides between B and A",
      "Other limits: Appendix A9",
    ], 7.65, 2.05, 5.08, 4.6);
    s.addNotes("B, our recommendation, uses an LFP cell we have not validated; its numbers are generic class values. The hold-out check shows the model under-predicts temperature rise about 2×, so we re-run every design with cells making twice the modelled heat, without telling the BMS. B then misses the charge limit by 0.02 K and A becomes the pick. You will see that flip live with the Unmodelled heat slider. One LFP charge test through the same fit pipeline settles it. The other limits, such as the proxy cell and the lumped thermal model, are in Appendix A9.");
  }

  // 11 · Demo
  {
    const s = slide();
    frame(s, n, { section: "Demo", tag: "Prototype & evidence · Technical feasibility",
      title: "The live demo runs the same study in six steps",
      source: "streamlit run app.py · python -m packforge --report packforge_report.html · script: docs/DEMO_SCRIPT.md" });
    const st = ["Baseline after a ride: 48 min hold, then REQ-03 fails", "Option C, the observer: passes, but slower",
      "A against B: the ranking and the three answers", "Validation: replay a 45 °C hold-out charge",
      "Unmodelled heat to 2×: the pick flips to A", "Download the offline report"];
    st.forEach((t, i) => {
      const y = 1.95 + i * 0.75;
      s.addShape("ellipse", { x: X0, y: y + 0.04, w: 0.5, h: 0.5, fill: { color: C.navy }, line: { color: C.navy } });
      s.addText(String(i + 1), { x: X0, y: y + 0.04, w: 0.5, h: 0.5, margin: 0, align: "center", valign: "middle",
        fontFace: F, fontSize: 18, bold: true, color: C.white });
      s.addText(t, { x: X0 + 0.75, y, w: 6.9, h: 0.58, margin: 0, fontFace: F, fontSize: 20, color: C.text, valign: "middle" });
    });
    box(s, 8.6, 1.95, 4.13, 4.45, C.panel);
    s.addText([
      run("31 s", { bold: true, fontSize: 44, color: C.navy, breakLine: true }),
      run("for the full study on a laptop: 4 designs, ride then charge, plus the 2× heat re-run", { fontSize: 18, color: C.text }),
    ], { x: 8.9, y: 2.15, w: 3.55, h: 2.6, margin: 0, fontFace: F, valign: "top", paraSpaceAfter: 6 });
    s.addText("Backup if the app fails: recorded clip, CLI output, HTML report", { x: 8.9, y: 5.0, w: 3.55, h: 1.2,
      margin: 0, fontFace: F, fontSize: 16, color: C.muted, valign: "top" });
    s.addNotes("Switch to the app now and follow docs/DEMO_SCRIPT.md: baseline after a ride, Option C, A against B and the recommendation, the Validation tab replay of a 45 °C hold-out charge, the heat slider to 2×, then download the report. The whole study takes about 30 seconds on this laptop. If the app does not respond within about 10 seconds, switch to the backup clip and keep talking over it.");
  }

  // 12 · Impact: business viability
  {
    const s = slide();
    frame(s, n, { section: "Impact", tag: "Business viability",
      title: "B costs 21 % less per usable kWh than the baseline, and C stops hot charging at no hardware cost",
      source: "Source: PackForge CLI. Costs are generic class values, not quotes; cycle life is a rule-of-thumb estimate." });
    const cats = ["B · LFP", "Baseline / C", "A · NMC + Al"];
    s.addChart(pres.charts.BAR, [
      { name: "B", labels: cats, values: [18205, 0, 0] },
      { name: "Others", labels: cats, values: [0, 23149, 24799] },
    ], { ...chartBase, x: X0, y: 1.9, w: 6.4, h: 4.6, barDir: "bar", barGrouping: "stacked", barGapWidthPct: 50,
      catAxisOrientation: "maxMin", chartColors: [C.blue, C.grey], showValue: true, dataLabelPosition: "inEnd",
      dataLabelFormatCode: '"₹"#,##0;;', dataLabelColor: C.white, dataLabelFontBold: true, showLegend: false,
      showTitle: true, title: "Cost per usable kWh (₹)", valAxisHidden: true, valGridLine: { style: "none" },
      valAxisMinVal: 0, valAxisMaxVal: 26000 });
    bodyText(s, [
      "C: a ₹0 retrofit for packs already on the road",
      "Conflicts surface before hardware, so the rig confirms instead of explores",
      "A new cell, option or study is a JSON file, not new code",
      "B also lasts about 3× as long in heat (~1,290 vs ~370 cycles, estimated)",
    ], 7.35, 2.05, 5.38, 4.6);
    s.addNotes("B is the cheapest per usable kWh, ₹18.2 k against ₹23.1 k for the baseline, and by our estimate lasts about three times as long in heat. Both numbers use generic class costs and a rule-of-thumb ageing model; tell the judges that. C has value today: a ₹0 fix for packs already built. The workbench itself saves prototypes, because the blind spot showed up in the model and a rig test only has to confirm it.");
  }

  // 13 · Conclusions (stays up during Q&A)
  {
    const s = slide();
    frame(s, n, { section: "Impact", tag: "Conclusions",
      title: "Build B, keep A ready, ship C today; one LFP charge test decides between B and A" });
    bodyText(s, [
      "The baseline BMS misses a 3.2 K hotspot and charges cells at 47.6 °C",
      "B (LFP) for new packs; A if mass is capped or LFP runs hotter; C as a ₹0 retrofit",
      "Evidence: a proxy cell checked on 60 hold-out logs; the LFP cell is not yet validated",
    ], X0, 2.05, 6.9, 4.2);
    box(s, 7.95, 1.95, 4.78, 3.0, C.blueTint);
    s.addText([
      run("Our ask", { bold: true, fontSize: 22, color: C.navy, breakLine: true }),
      run("LFP cells and supervised rig time for one LFP charge test", { fontSize: 20, color: C.text, breakLine: true }),
      run("≤ 2S protected cells, inline fuse, fireproof bag, hard cut-offs in firmware, never unattended", { fontSize: 16, color: C.muted }),
    ], { x: 8.25, y: 2.2, w: 4.18, h: 2.6, margin: 0, fontFace: F, valign: "top", paraSpaceAfter: 12 });
    s.addText([
      run("Falak Anwar", { bold: true }), run(" · office.falakanwar@gmail.com     "),
      run("Zaid Alam", { bold: true }), run(" · zaidlc319@gmail.com     "),
      run("github.com/gitFa07/battery-energy-system", { color: C.blue,
        hyperlink: { url: "https://github.com/gitFa07/battery-energy-system" } }),
    ], { x: X0, y: 6.45, w: CW, h: 0.45, margin: 0, fontFace: F, fontSize: 14, color: C.text, valign: "middle" });
    s.addNotes("Build B for new packs. Keep A ready: it is the robust choice if the LFP cell runs hotter than modelled. Ship C to packs already on the road at no hardware cost. The next step is one LFP charge test through the same pipeline, then a pack-level log. Our ask: LFP cells and supervised rig time to run that test safely. Leave this slide up during questions and invite questions or feedback.");
  }

  // References
  {
    const s = slide();
    frame(s, n, { section: "Backup", tag: "References", title: "References" });
    const refs = [
      [run("Yao, J., Droese, & Kowal (2026). "), run("Lithium-Ion Battery Internal Temperature Dataset", { italic: true }),
        run(". Technische Universität Berlin, EET. "), run("https://doi.org/10.14279/depositonce-25110", { color: C.blue,
          hyperlink: { url: "https://doi.org/10.14279/depositonce-25110" } }),
        run(". CC BY 4.0. LG INR21700 M50LT cells. Our changes: current sign flipped, columns renamed, values rounded, charges cut and resampled to 1 s.")],
      [run("Tata Elxsi (2026). "), run("TELIPORT Season 4, Case Study 2: Reusable Digital Platform for Designing Battery Energy System", { italic: true }), run(". Hackathon brief.")],
      [run("AIS-156, Amendment 3, Annex 8K. Cited for the sensor count only; no design is claimed compliant.")],
      [run("PackForge (2026). CLI run of studies/escooter_48v; calibration record data/validation/calibration_nmc21700_5ah.json. "),
        run("github.com/gitFa07/battery-energy-system", { color: C.blue, hyperlink: { url: "https://github.com/gitFa07/battery-energy-system" } })],
    ];
    const items = [];
    refs.forEach((r, i) => r.forEach((x, k) => items.push(k === r.length - 1 && i < refs.length - 1
      ? { text: x.text, options: { ...x.options, breakLine: true } } : x)));
    s.addText(items, { x: X0, y: 1.6, w: CW, h: 4.3, margin: 0, fontFace: F, fontSize: 16, color: C.text,
      valign: "top", paraSpaceAfter: 14 });
    caption(s, "NMC 21700 5 Ah and LFP cell values are generic class values, not a named datasheet. SYNTHETIC_* logs come from our own model: a method check for the fitter, never evidence.",
      X0, 6.0, CW, 0.75, { fontSize: 14 });
    s.addNotes("The dataset attribution is required by its CC BY 4.0 licence.");
  }

  // Appendix
  const appx = (id, title, tag, source) => {
    const s = slide();
    frame(s, n, { section: "Backup", tag: `Appendix ${id}${tag ? " · " + tag : ""}`, title: `${id} · ${title}`, source });
    return s;
  };
  const small = (o) => tableOpts({ fontSize: 16, ...o });

  {
    const s = appx("A1", "The study sets 11 requirements; four are must-pass", "Problem understanding",
      "Source: studies/escooter_48v/study.json. Orange rows: where the baseline gets into trouble.");
    const req = [
      ["REQ-01", "Nominal voltage fits 48 V controller", "44–56 V", "must"],
      ["REQ-02", "Usable energy, urban cycle at 40 °C", "≥ 2,000 Wh", "must"],
      ["REQ-03", "Cell temperature while charging", "≤ 45 °C", "must"],
      ["REQ-04", "Cell temperature while riding", "≤ 55 °C", "must"],
      ["REQ-05", "Charge time, plug-in → 80 %", "≤ 120 min", "should"],
      ["REQ-06", "Cell-to-cell temperature spread", "≤ 5 K", "should"],
      ["REQ-07", "Blind spot: hottest cell − BMS view", "≤ 3 K", "should"],
      ["REQ-08", "Pack mass", "≤ 16 kg", "should"],
      ["REQ-09", "Pack volume", "≤ 12 L", "should"],
      ["REQ-10", "Pack cost", "≤ ₹60,000", "should"],
      ["REQ-11", "Cycle life in hot climate", "≥ 1,000 cycles", "should"],
    ];
    const hot = new Set(["REQ-03", "REQ-05", "REQ-07"]);
    const rows = [[th("ID"), th("Requirement"), th("Limit"), th("Type")],
      ...req.map(r => r.map(t => td(t, hot.has(r[0]) ? { fill: { color: C.alertTint } } : {})))];
    s.addTable(rows, small({ x: X0, y: 1.95, w: 9.5, colW: [1.3, 5.0, 1.9, 1.3], rowH: 0.4 }));
    s.addNotes("Backup for Q&A. Must-requirements disqualify a design; should-requirements become stated risks.");
  }
  {
    const s = appx("A2", "Hold-out voltage error stays below 45 mV in the operating window", "Prototype & evidence",
      "Data: Yao, Droese & Kowal (2026), TU Berlin, DOI 10.14279/depositonce-25110, CC BY 4.0. Record: data/validation/calibration_nmc21700_5ah.json");
    const rows = [
      [th("Hold-out set (45 °C)"), th("Logs"), th("V RMSE, SOC ≥ 10 % (median / max)"), th("V RMSE, full range"), th("T RMSE (median)"), th("T rise, measured / model")],
      [td("Drive cycles"), td("30"), td("18 / 43 mV"), td("38 / 122 mV"), td("0.23 K"), td("2.0 / 1.0 K")],
      [td("1C charges"), td("30"), td("17 / 22 mV"), td("22 / 25 mV"), td("0.55 K"), td("3.4 / 1.6 K")],
    ];
    s.addTable(rows, small({ x: X0, y: 1.95, w: CW, colW: [2.3, 0.9, 2.9, 2.1, 1.8, 2.133], rowH: [0.8, 0.5, 0.5] }));
    bodyText(s, [
      "Fit on cell AM23NMC00103 at 25 and 35 °C; 3 cells × (10 drives + 10 charges) at 45 °C held out",
      "Below 10 % SOC the voltage error grows to about 0.1–0.9 V near cut-off",
      "Under-predicted heating: no SOC-dependent resistance or entropic heat in the model",
    ], X0, 3.9, CW, 2.8, { fontSize: 18 });
    s.addNotes("Backup for Q&A. Hold-out logs never enter the fit. Voltage RMSE is reported for SOC at or above 10 % and for the full range side by side.");
  }
  {
    const s = appx("A3", "Full KPI table: the baseline is the only design disqualified", "Prototype & evidence",
      "Source: python -m packforge studies/escooter_48v, calibrated NMC cell. B's LFP cell is not validated.");
    const c = (t, o = {}) => td(t, { align: "center", ...o });
    const bad = (t) => c(t, { bold: true, color: C.alert });
    const L = (t) => td(t, { bold: true });
    const rows = [
      [th("Metric"), th("Baseline", { align: "center" }), th("A", { align: "center" }), th("B", { align: "center" }), th("C", { align: "center" })],
      [L("Charge time, plug-in → 80 %"), c("244 min"), c("92 min"), c("97 min"), c("277 min")],
      [L("Thermal hold"), c("48 min"), c("0 min"), c("0 min"), c("90 min")],
      [L("Peak T, charging"), bad("47.6 °C fail"), c("44.0 °C"), c("43.7 °C"), c("44.5 °C")],
      [L("Peak T, riding"), c("53.4 °C"), c("44.1 °C"), c("43.1 °C"), c("53.4 °C")],
      [L("Blind spot"), bad("3.2 K warn"), c("0.0 K"), c("0.1 K"), c("0.2 K")],
      [L("Pack mass"), c("12.3 kg"), c("13.5 kg"), bad("22.7 kg warn"), c("12.3 kg")],
      [L("₹ per usable kWh"), c("23.1 k"), c("24.8 k"), c("18.2 k"), c("23.1 k")],
      [L("Cycle life (estimate)"), c("~370"), c("~405"), c("~1,290"), c("~370")],
      [L("Ranking"), c("disqualified"), c("2nd"), c("1st", { bold: true, color: C.blue }), c("3rd")],
    ];
    s.addTable(rows, small({ x: X0, y: 1.95, w: 10.0, colW: [3.6, 1.6, 1.6, 1.6, 1.6], rowH: 0.45 }));
    s.addNotes("Backup for Q&A. Cycle life is a rule of thumb, not validated; costs and masses are generic class values.");
  }
  {
    const s = appx("A4", "Students and pack engineers lose time to copied parameters and late conflicts", "Desirability",
      "PackForge: users and pain points");
    const rows = [
      [th("Pain point"), th("Today"), th("With PackForge")],
      [td("Siloed data", { bold: true }), td("Electrical, thermal and BMS models with copied parameters"), td("One design file shared by every model")],
      [td("Late conflicts", { bold: true }), td("A blind spot like the baseline's shows up on the first hot prototype"), td("It shows up in the model, with its cause chain")],
      [td("Hot-climate safety", { bold: true }), td("E-2W packs in India charge in 40 °C heat, often right after a ride"), td("That is the design case")],
    ];
    s.addTable(rows, small({ x: X0, y: 1.95, w: CW, colW: [2.6, 5.1, 4.433], rowH: [0.5, 0.85, 0.85, 0.85] }));
    bodyText(s, ["Students and new engineers: see why a design fails, with the cause chain across cell, thermal and BMS",
      "Pack engineers: screen options before hardware on the same requirements and scenarios"], X0, 5.4, CW, 1.4, { fontSize: 18 });
    s.addNotes("Backup for Q&A on desirability.");
  }
  {
    const s = appx("A5", "Six cross-checks and 23 automated tests guard the physics", "Engineering quality",
      "Source: tests/test_packforge.py · model conventions in CLAUDE.md");
    const rows = [
      [th("Check"), th("Result")],
      [td("Adiabatic heat balance: heat generated vs cell temperature rise"), td("within ±2 %")],
      [td("Delivered energy vs nominal, ending on the undervoltage cut-off"), td("0.9–1.06×")],
      [td("Time step 2 s vs 1 s"), td("KPIs within 0.4 %, ΔT within 0.05 K")],
      [td("Simulated charge time vs independent hand-calc bound, cold start"), td("0.95–1.3×")],
      [td("Observer-controlled charge with ±30 % error in its cooling model"), td("peak ≤ 45 °C")],
      [td("Automated tests: physics, conflicts, calibration, ranking, report"), td("23 tests, about 90 s")],
    ];
    s.addTable(rows, small({ x: X0, y: 1.95, w: CW, colW: [8.1, 4.033], rowH: 0.6 }));
    s.addNotes("Backup for Q&A on engineering quality. Every placeholder value is an assumption with an ID that the traceability tab links to the results it affects.");
  }
  {
    const s = appx("A6", "Five features link each failure to its cause, its sensors and its evidence", "Innovation",
      "PackForge: checks.py · sim.py (observer) · engine.py (Monte Carlo, traceability)");
    const rows = [
      [th("Feature"), th("What it does")],
      [td("Cause-explaining conflict checker", { bold: true }), td("Each failure names the subsystems, the cause chain and candidate fixes")],
      [td("Sensor blind-spot metric", { bold: true }), td("How far the hottest cell runs above what the BMS acts on, for any sensor count and placement")],
      [td("Virtual hotspot sensor", { bold: true }), td("A thermal observer in the BMS: a ₹0 retrofit, checked at ±30 % cooling-model error")],
      [td("Variation Monte Carlo", { bold: true }), td("Cell-to-cell capacity and resistance spread; every sampled pack simulated in one batch")],
      [td("Evidence-ladder traceability", { bold: true }), td("Requirement → metric → assumption; every number tagged from datasheet up to measured")],
    ];
    s.addTable(rows, small({ x: X0, y: 1.95, w: CW, colW: [3.9, 8.233], rowH: 0.7 }));
    s.addNotes("Backup for Q&A on innovation.");
  }
  {
    const s = appx("A7", "Everything runs on a laptop, and any bench test stays low-voltage and supervised", "Technical feasibility",
      "Timing: one CLI run of studies/escooter_48v on the team laptop (31 s)");
    const rows = [
      [th("Item"), th("Detail")],
      [td("Run time", { bold: true }), td("31 s for the whole study: 4 designs, ride then charge, plus the 2× heat re-run")],
      [td("Data", { bold: true }), td("Public CC BY 4.0 dataset; anyone can re-run the fit and the hold-out check")],
      [td("Stack", { bold: true }), td("Python: numpy, scipy, pydantic, pandas, plotly, Streamlit. CLI, UI and report share one core")],
      [td("No dataset", { bold: true }), td("Every value falls back to a stated assumption with its evidence level")],
      [td("Rig safety", { bold: true }), td("≤ 2S protected cells, inline fuse, fireproof bag, never unattended, hard cut-offs in firmware")],
    ];
    s.addTable(rows, small({ x: X0, y: 1.95, w: CW, colW: [2.4, 9.733], rowH: 0.7 }));
    s.addNotes("Backup for Q&A on feasibility and safety.");
  }
  {
    const s = appx("A8", "The cell is an equivalent circuit with one RC branch, fitted to the proxy cell", "Engineering quality",
      "Source: data/validation/calibration_nmc21700_5ah.json. Test-rig cooling is fitted but never carried over to a pack.");
    bodyText(s, [
      "Cell: OCV(SOC) + R0 + one RC branch; R0 and R1 scale with Arrhenius temperature",
      "Heat per cell: I²R0 + V_rc²/R1",
      "Thermal: one node per cell; loss h_eff × surface; 4‑neighbour conduction",
      "BMS: CC-CV, derating on sensors or observer; OV, UV and OT protection",
    ], X0, 1.95, 6.3, 4.8, { fontSize: 18 });
    const rows = [
      [th("Parameter"), th("Generic"), th("Calibrated")],
      [td("R0"), td("0.020 Ω"), td("0.0267 Ω")],
      [td("R1"), td("0.012 Ω"), td("0.0230 Ω")],
      [td("τ"), td("30 s"), td("46 s")],
      [td("Capacity"), td("5.0 Ah"), td("4.874 Ah")],
    ];
    s.addTable(rows, small({ x: 7.35, y: 1.95, w: 5.38, colW: [1.9, 1.74, 1.74], rowH: 0.55 }));
    s.addNotes("Backup for Q&A on the model.");
  }
  {
    const s = appx("A9", "Known limits: proxy cell, lumped thermal model, unvalidated LFP and ageing", "Engineering quality",
      "Source: ROADMAP.md, known limitations");
    const cols = [["Data and validation", [
      "NMC calibrated on a proxy cell in a chamber: single cells, not our cell, not a pack",
      "Temperature rise under-predicted ~2×: covered by the 2× re-run, not fixed",
      "LFP cell, costs and masses are generic class values; LFP not validated",
      "Ageing is a rule of thumb, not validated",
      "Below 10 % SOC the voltage error grows to ~0.1–0.9 V"]],
    ["Model and scope", [
      "Lumped thermal model with an effective h; no CFD, no enclosure air node",
      "One node per cell; on the proxy cell the core runs up to 4.6 K above the surface",
      "The observer shares the plant's model structure; real error will exceed the ±30 % tested",
      "Synthetic drive profile, not a homologation cycle; one 48 V pack only",
      "No design claimed AIS-156 compliant (Amd. 3, Annex 8K asks for ≥ 4 sensors)"]]];
    cols.forEach(([h, items], i) => {
      const x = i ? 6.87 : X0;
      s.addText(h, { x, y: 1.75, w: 5.86, h: 0.4, margin: 0, fontFace: F, fontSize: 18, bold: true, color: C.navy });
      bodyText(s, items, x, 2.3, 5.86, 4.5, { fontSize: 16, paraSpaceAfter: 10 });
    });
    s.addNotes("Backup for Q&A. Say these before the judges ask.");
  }

  await pres.writeFile({ fileName: OUT });
  console.log("wrote", OUT, n, "slides");
}

main().catch(e => { console.error(e); process.exit(1); });
