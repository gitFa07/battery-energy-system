"""Mechanical packaging and itemised BOM.

    V_pack = N · V_cell / PACKING_FRACTION · ENCLOSURE_FACTOR + V_BMS_BAY + V_cooling
    m_pack = N · (m_cell + m_busbar + m_holder) + m_cooling + m_BMS + m_fuse + n_NTC · m_NTC + m_harness
             + ENCLOSURE_KG_PER_L · V_pack
    cost   = same structure in $, plus assembly per cell
All constants below are class assumptions for a small e-2W pack (ids referenced by traceability).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from src.models.schemas import BusbarSpec, CellSpec, CoolingSpec, ModuleDesignInput, ProtectionSpec

PACKING_FRACTION = math.pi / 4   # A-ME-01: cylinders on a square grid in plastic holders
ENCLOSURE_FACTOR = 1.6           # A-ME-02: walls, clearances, spacers around the cell block
BMS_BAY_L = 0.8                  # A-ME-03: BMS board, fuse, connectors
HOLDER_KG_PER_CELL = 0.004       # A-ME-04
HARNESS_KG = 0.4                 # A-ME-05: wiring harness, connectors, sense leads
ENCLOSURE_KG_PER_L = 0.18        # A-ME-06: Al/ABS enclosure mass per litre of pack
HOLDER_USD_PER_CELL = 0.03       # A-EC-01
ASSEMBLY_USD_PER_CELL = 0.12     # A-EC-02: welding, test, labour (India)
HARNESS_USD = 12.0               # A-EC-03
ENCLOSURE_USD_PER_L = 3.0        # A-EC-04


@dataclass(frozen=True)
class PackMechanical:
    volume_l: float
    mass_kg: float
    bom_cost_usd: float
    mass_breakdown_kg: dict[str, float]
    cost_breakdown_usd: dict[str, float]


def pack_mechanical(design: ModuleDesignInput, cell: CellSpec, cooling: CoolingSpec, busbar: BusbarSpec,
                    fuse: ProtectionSpec, bms: ProtectionSpec, ntc: ProtectionSpec) -> PackMechanical:
    n = design.n_cells
    volume = n * cell.volume_l / PACKING_FRACTION * ENCLOSURE_FACTOR + BMS_BAY_L + cooling.volume_l
    mass = {
        "cells": n * cell.mass_kg,
        "busbars": n * busbar.mass_per_cell_kg,
        "holders": n * HOLDER_KG_PER_CELL,
        "cooling": cooling.mass_kg,
        "bms": bms.mass_kg,
        "fuse": fuse.mass_kg,
        "ntc": design.n_ntc * ntc.mass_kg,
        "harness": HARNESS_KG,
        "enclosure": ENCLOSURE_KG_PER_L * volume,
    }
    cost = {
        "cells": n * cell.cost_usd,
        "busbars": n * busbar.cost_per_cell_usd,
        "holders": n * HOLDER_USD_PER_CELL,
        "assembly": n * ASSEMBLY_USD_PER_CELL,
        "cooling": cooling.cost_usd,
        "bms": bms.cost_usd,
        "fuse": fuse.cost_usd,
        "ntc": design.n_ntc * ntc.cost_usd,
        "harness": HARNESS_USD,
        "enclosure": ENCLOSURE_USD_PER_L * volume,
    }
    return PackMechanical(volume, sum(mass.values()), sum(cost.values()), mass, cost)
