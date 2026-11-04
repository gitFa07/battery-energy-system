"""System configuration: ambient/thermal limits and the 7 hard requirements (TASK.md §1.1)."""

from __future__ import annotations

from pathlib import Path

from src.models.schemas import HardRequirement

ROOT = Path(__file__).resolve().parent.parent
DATASHEET_DIR = ROOT / "data" / "datasheets"

AMBIENT_REF_C = 40.0        # design ambient for the e-scooter study
T_PEAK_LIMIT_C = 50.0       # REQ-TH-01 limit
BMS_CUTOFF_C = 55.0         # BMS thermal cutoff (charging stops)
CHARGE_SOC_WINDOW = (0.10, 0.80)

REQUIREMENTS: list[HardRequirement] = [
    HardRequirement(id="REQ-EL-01", text="Nominal voltage window 48 V", metric="v_nom_v", min=44.0, max=54.0,
                    unit="V", cutoff="Outside inverter/controller limits"),
    HardRequirement(id="REQ-EL-02", text="Usable energy", metric="usable_energy_kwh", min=2.40, unit="kWh",
                    cutoff="Insufficient range (< 2.40 kWh)"),
    HardRequirement(id="REQ-TH-01", text=f"Peak cell temperature at {AMBIENT_REF_C:g} °C ambient",
                    metric="t_peak_c", max=T_PEAK_LIMIT_C, unit="°C",
                    cutoff=f"BMS thermal cutoff at {BMS_CUTOFF_C:g} °C"),
    HardRequirement(id="REQ-CH-01", text="Fast-charge turnaround 10-80 % SoC", metric="charge_time_10_80_min",
                    max=45.0, unit="min", cutoff="Exceeds turnaround window"),
    HardRequirement(id="REQ-ME-01", text="Module total mass", metric="mass_kg", max=18.0, unit="kg",
                    cutoff="Exceeds e-scooter chassis structural envelope"),
    HardRequirement(id="REQ-ME-02", text="Module volume", metric="volume_l", max=12.0, unit="L",
                    cutoff="Exceeds under-seat bay envelope"),
    HardRequirement(id="REQ-EC-01", text="Target BOM cost", metric="bom_cost_usd", max=360.0, unit="$",
                    cutoff="Exceeds commercial unit cost ceiling"),
]

REQUIREMENTS_BY_ID = {r.id: r for r in REQUIREMENTS}
