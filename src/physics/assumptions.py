"""Registry of modelling assumptions referenced by id in the physics code and the traceability chain."""

from __future__ import annotations

from src.physics import electrical as el
from src.physics import mechanical_bom as mb
from src.physics import thermal as th

ASSUMPTIONS: dict[str, str] = {
    "A-EL-01": f"Cell resistance = datasheet R0 × {1 + el.BOL_R_MARGIN:.2f} (ageing/spread margin), held at its "
               "25 °C value (conservative at 40-55 °C).",
    "A-EL-02": f"Peak discharge for protection sizing = {el.PEAK_DISCHARGE_C:g} C (acceleration).",
    "A-EL-03": "Generic OCV(SoC) class curves per chemistry; used only for voltage traces.",
    "A-EL-04": "Usable energy = nominal energy × design DoD window; no rate-dependent capacity loss.",
    "A-TH-01": f"Reversible heat with class-average dU/dT (NMC {th.ENTROPIC_V_K['NMC']*1e3:g} mV/K, "
               f"LFP {th.ENTROPIC_V_K['LFP']*1e3:g} mV/K); the real sign varies with SoC.",
    "A-TH-02": f"Hottest-cell core runs {th.R_CORE_K_W:g} K/W × cell heat above the pack node (radial conduction).",
    "A-TH-03": "One lumped thermal node: all cells + cooling hardware; no cell-to-cell gradient beyond A-TH-02.",
    "A-TH-04": f"Duty cycle: ride at {th.RIDE_C:g} C from {th.SOC_RIDE_START:.0%} to 10 % SoC, plug in at once, "
               "charge 10 → 80 %.",
    "A-TH-05": "Cooling thermal resistances are estimates from typical h ranges (see cooling_topologies.json).",
    "A-TH-06": "BMS derates linearly between 50 and 55 °C on the pack (NTC) temperature.",
    "A-ME-01": f"Cells on a square grid in holders: packing fraction {mb.PACKING_FRACTION:.3f}.",
    "A-ME-02": f"Enclosure volume factor {mb.ENCLOSURE_FACTOR:g} + {mb.BMS_BAY_L:g} L BMS bay; enclosure "
               f"{mb.ENCLOSURE_KG_PER_L:g} kg/L; harness {mb.HARNESS_KG:g} kg.",
    "A-EC-01": f"BOM per cell: holder ${mb.HOLDER_USD_PER_CELL:g}, assembly ${mb.ASSEMBLY_USD_PER_CELL:g}; harness "
               f"${mb.HARNESS_USD:g}; enclosure ${mb.ENCLOSURE_USD_PER_L:g}/L. Part costs are class estimates.",
    "A-CL-01": "Cell values are generic 21700 class values, not a named part; the LFP cell is not validated.",
}
