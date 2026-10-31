// PackForge one-slider for the initial submission (pptxgenjs). Same numbers and style as build.js.
const pptxgen = require("pptxgenjs");

const OUT = process.argv[2] || "PackForge_one_slider.pptx";
const C = {
  navy: "1F4E79", blue: "2E75B6", alert: "C2410C",
  blueTint: "DEEAF6", panel: "F2F4F7", text: "262626", muted: "6B7280", grey: "A6ADB4",
};
const F = "Calibri";
const W = 13.333, X0 = 0.5, CW = W - 2 * X0;

const nb = (t) => t
  .replace(/(\d) (?=%|°C|K\b|min\b|mV\b|Wh\b|kg\b|L\b|Ah\b|s\b|k\b|V\b|cycles\b|→)/g, "$1 ")
  .replace(/(≤|≥|~|±|→|₹) /g, "$1 ")
  .replace(/\b(REQ|AIS)-(\d)/g, "$1‑$2");
const run = (text, o = {}) => ({ text: nb(text), options: o });
const bullets = (items) => items.map((t, i) => {
  const parts = Array.isArray(t) ? t : [[t]];
  return parts.map(([s, o = {}], k) => run(s, { ...o, ...(k === 0 ? { bullet: { indent: 12 } } : {}),
    ...(k === parts.length - 1 && i < items.length - 1 ? { breakLine: true } : {}) }));
}).flat();

function panel(s, x, y, w, h, head, tag, items, fill = C.panel, fontSize = 12) {
  s.addShape("rect", { x, y, w, h, fill: { color: fill }, line: { color: fill } });
  s.addText([run(head, { bold: true, color: C.navy, fontSize: 15 }), run(`   ${tag}`, { color: C.muted, fontSize: 10.5 })],
    { x: x + 0.2, y: y + 0.12, w: w - 0.4, h: 0.35, margin: 0, fontFace: F, valign: "middle" });
  s.addText(bullets(items), { x: x + 0.2, y: y + 0.55, w: w - 0.4, h: h - 0.65, margin: 0, fontFace: F,
    fontSize, color: C.text, valign: "top", paraSpaceAfter: 5 });
}

async function main() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE";
  pres.title = "PackForge: one-slider";
  pres.author = "Falak Anwar, Zaid Alam";
  const s = pres.addSlide();
  s.background = { color: "FFFFFF" };

  s.addText(nb("TELIPORT Season 4 · Tata Elxsi · Case Study 2: Reusable Digital Platform for Designing Battery Energy System"),
    { x: X0, y: 0.22, w: 9.3, h: 0.3, margin: 0, fontFace: F, fontSize: 11, color: C.muted });
  s.addText("PackForge · Falak Anwar · Zaid Alam", { x: W - X0 - 3.5, y: 0.22, w: 3.5, h: 0.3, margin: 0,
    fontFace: F, fontSize: 11, bold: true, color: C.navy, align: "right" });
  s.addText(nb("PackForge shows that a 48 V scooter pack charges hidden cells at 47.6 °C after a hot ride, and ranks three fixes before any hardware is built"),
    { x: X0, y: 0.55, w: CW, h: 0.95, margin: 0, fontFace: F, fontSize: 24, bold: true, color: C.navy, valign: "top" });

  // Row 1: problem, platform, evidence
  const top = 1.62, ph = 2.38, gap = 0.2, pw = (CW - 2 * gap) / 3;
  panel(s, X0, top, pw, ph, "The problem", "Problem understanding · Desirability", [
    "48 V e-scooter pack (13S10P NMC, 2,263 Wh) at 40 °C, plugged in straight after the ride",
    "Edge NTCs read 3.2 K low; after a 48 min hold the BMS charges interior cells at 47.6 °C (limit 45 °C)",
    "For students learning why designs fail and pack engineers choosing what to prototype",
  ]);
  panel(s, X0 + pw + gap, top, pw, ph, "The platform", "Feasibility · Innovation", [
    "One design file feeds an electro-thermal sim, a sensor-only BMS and a conflict checker (11 requirements, 14 interface rules)",
    "New: cause chains with fixes, blind-spot metric, virtual hotspot sensor, evidence levels",
    "31 s per study on a laptop; a new option is one JSON file",
  ]);
  panel(s, X0 + 2 * (pw + gap), top, pw, ph, "The evidence", "Engineering quality · Prototype", [
    "Cell fitted on public TU Berlin data (proxy cell LG M50LT) at 25 and 35 °C",
    "60 hold-out logs at 45 °C: voltage RMSE 17–18 mV (median)",
    "Heating underestimated ~2×, so every design is re-run at 2× heat",
    "23 automated tests incl. heat balance and a hand‑calc bound",
  ]);

  // Row 2: the one exhibit (left) and the recommendation (right)
  const y2 = top + ph + 0.2, h2 = 6.78 - y2;
  const cats = ["Baseline · 244 min", "A: NMC + Al plate · 92 min", "B: LFP 16S8P · 97 min", "C: + BMS observer · 277 min"];
  s.addChart(pres.charts.BAR, [
    { name: "Thermal hold (no current)", labels: cats, values: [48.2, 0, 0, 89.5] },
    { name: "Charging", labels: cats, values: [195.5, 92.1, 97.4, 187.1] },
  ], { x: X0, y: y2, w: 6.3, h: h2, barDir: "bar", barGrouping: "stacked", barGapWidthPct: 45,
    catAxisOrientation: "maxMin", chartColors: [C.alert, C.navy], showValue: true, dataLabelPosition: "ctr",
    dataLabelFormatCode: "0;;", dataLabelColor: "FFFFFF", dataLabelFontBold: true, dataLabelFontSize: 11,
    dataLabelFontFace: F, showLegend: true, legendPos: "b", legendFontSize: 11, legendFontFace: F,
    showTitle: true, title: "Charge time, plug-in → 80 % after a 40 °C ride (min)", titleFontSize: 12, titleFontFace: F,
    titleColor: C.text, catAxisLabelColor: C.text, catAxisLabelFontSize: 11, catAxisLabelFontFace: F,
    valAxisLabelColor: C.muted, valAxisLabelFontSize: 10, valAxisLabelFontFace: F, valAxisMinVal: 0,
    valAxisMaxVal: 300, valAxisMajorUnit: 60, valGridLine: { color: "E5E7EB", size: 0.5 }, catGridLine: { style: "none" } });
  // REQ-05 limit at 120 min; plot-area x positions measured from the PowerPoint render.
  const PX0 = Number(process.env.PX0 || 2.475), PX300 = Number(process.env.PX300 || 6.54);
  const PY0 = Number(process.env.PY0 || y2 + 0.67), PY1 = Number(process.env.PY1 || y2 + h2 - 0.51);
  const x120 = PX0 + 0.4 * (PX300 - PX0);
  s.addShape("line", { x: x120, y: PY0, w: 0, h: PY1 - PY0, line: { color: C.alert, width: 1.75, dashType: "dash" } });
  s.addText(nb("120 min limit"), { x: x120 + 0.07, y: Number(process.env.LY || PY0 + 0.45), w: 1.4, h: 0.28, margin: 0,
    fontFace: F, fontSize: 11, bold: true, color: C.alert, valign: "middle" });

  const rx = X0 + 6.3 + 0.25, rw = W - X0 - rx;
  s.addShape("rect", { x: rx, y: y2, w: rw, h: h2, fill: { color: C.blueTint }, line: { color: C.blueTint } });
  s.addText([run("Recommendation", { bold: true, color: C.navy, fontSize: 15 }),
    run("   Business viability", { color: C.muted, fontSize: 10.5 })],
    { x: rx + 0.2, y: y2 + 0.12, w: rw - 0.4, h: 0.35, margin: 0, fontFace: F, valign: "middle" });
  s.addText(bullets([
    [["B · LFP for new packs: ", { bold: true }], ["97 min, ₹18.2 k per usable kWh (lowest), ~3× cycle life (estimate); over mass and volume targets"]],
    [["A · NMC + Al plate if mass is capped: ", { bold: true }], ["92 min, +₹2.7 k per pack; the only design that passes at 2× heat"]],
    [["C · BMS observer for packs already built: ", { bold: true }], ["₹0, safe at 44.5 °C, 277 min"]],
    [["Top risk: ", { bold: true, color: C.alert }], ["the LFP cell is not validated; at 2× heat B misses the limit by 0.02 K and A becomes the pick", { color: C.alert }]],
    [["Next step: ", { bold: true }], ["a supervised LFP charge test (≤ 2S, fused) decides B or A"]],
  ]), { x: rx + 0.2, y: y2 + 0.55, w: rw - 0.4, h: h2 - 0.65, margin: 0, fontFace: F, fontSize: 12,
    color: C.text, valign: "top", paraSpaceAfter: 5 });

  s.addText([
    run("Data: Yao, Droese & Kowal (2026), TU Berlin, DOI 10.14279/depositonce-25110, CC BY 4.0. Costs and masses are generic class values. No design is claimed AIS-156 compliant. ", { color: C.muted }),
    run("github.com/gitFa07/battery-energy-system", { color: C.blue, hyperlink: { url: "https://github.com/gitFa07/battery-energy-system" } }),
    run(" · office.falakanwar@gmail.com · zaidlc319@gmail.com", { color: C.muted }),
  ], { x: X0, y: 6.9, w: CW, h: 0.45, margin: 0, fontFace: F, fontSize: 9.5, valign: "top" });

  s.addNotes("One-slider for the initial submission. Every number comes from the CLI run of studies/escooter_48v and the calibration record, the same sources as docs/PackForge_pitch.pptx.");
  await pres.writeFile({ fileName: OUT });
  console.log("wrote", OUT);
}

main().catch(e => { console.error(e); process.exit(1); });
