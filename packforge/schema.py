"""Design schema: the single source of truth exchanged between all subsystem models.

Every model reads from a `Design` and writes into a metrics dict, so a change in one
subsystem (e.g. cooling) propagates to every other result without hand-copying values.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

Evidence = Literal["datasheet", "assumption", "calculated", "simulated", "estimated", "measured"]
Subsystem = Literal["cell", "electrical", "thermal", "mechanical", "sensing", "protection", "control", "cost"]


class Assumption(BaseModel):
    id: str
    text: str
    source: str = "team assumption"
    affects: list[Subsystem] = Field(default_factory=list)


class Cell(BaseModel):
    id: str
    name: str
    chemistry: Literal["NMC", "LFP", "NCA", "LMFP"]
    capacity_ah: float
    v_nom: float
    v_max: float
    v_min: float
    max_charge_a: float
    max_discharge_a: float
    r0_ohm: float = Field(description="ohmic resistance at 25 C")
    r1_ohm: float = Field(description="polarisation resistance of the 1-RC branch at 25 C")
    tau_s: float = Field(description="RC time constant")
    r_temp_k: float = Field(3000.0, description="Arrhenius coefficient Ea/R for resistance [K]")
    mass_kg: float
    diameter_mm: float
    height_mm: float
    cp_j_kgk: float
    heat_factor: float = Field(1.0, description="multiplies modelled heat in the real cells only (the BMS observer "
                                                "does not know it) — sensitivity knob for unmodelled heat")
    t_charge_min_c: float
    t_charge_max_c: float
    t_discharge_max_c: float
    cycle_life_ref: float = Field(description="cycles to 80% SOH at 25 C reference conditions")
    aging_ea_over_r_k: float = Field(3600.0, description="Arrhenius coefficient for ageing [K]")
    cost_inr: float
    ocv_soc: list[float]
    ocv_v: list[float]
    sources: list[str] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ocv_table(self) -> "Cell":
        if len(self.ocv_soc) != len(self.ocv_v) or sorted(self.ocv_soc) != self.ocv_soc:
            raise ValueError(f"{self.id}: OCV table must be same length and sorted by SOC")
        return self

    @property
    def surface_m2(self) -> float:
        d, h = self.diameter_mm / 1000, self.height_mm / 1000
        return 3.141592653589793 * d * h + 2 * 3.141592653589793 * (d / 2) ** 2

    @property
    def volume_l(self) -> float:
        d, h = self.diameter_mm / 100, self.height_mm / 100  # dm
        return 3.141592653589793 * (d / 2) ** 2 * h


class Topology(BaseModel):
    series: int = Field(ge=1)
    parallel: int = Field(ge=1)


class Interconnect(BaseModel):
    cell_tab_resistance_ohm: float = Field(description="weld/tab resistance added to each cell")
    string_resistance_ohm: float = Field(description="busbars + cables in series with the pack")
    busbar_ampacity_a: float
    fuse_rating_a: float


class Cooling(BaseModel):
    type: Literal["passive", "conduction_plate", "forced_air", "liquid_plate"]
    h_eff_w_m2k: float = Field(description="effective cell-to-sink coefficient referenced to cell surface")
    edge_factor: float = Field(1.0, description="multiplier for perimeter cells (better exposed)")
    g_neighbor_w_k: float = Field(description="cell-to-cell conductance through holders/busbars/plate")
    sink_temp_c: float | None = Field(None, description="None = ambient")
    parasitic_w: float = 0.0
    mass_kg: float = 0.0
    volume_l: float = 0.0
    cost_inr: float = 0.0


class Sensing(BaseModel):
    n_temp_sensors: int = Field(ge=1)
    placement: Literal["edge", "spread", "center"] | list[tuple[int, int]] = "spread"
    sensor_cost_inr: float = 40.0


class Bms(BaseModel):
    max_series: int
    cost_inr: float
    mass_kg: float


class Protection(BaseModel):
    ov_cell_v: float
    uv_cell_v: float
    ot_charge_c: float
    ot_discharge_c: float
    oc_discharge_a: float


class Control(BaseModel):
    charge_c_rate: float
    cv_v_cell: float
    cutoff_c_rate: float = 0.05
    derate_start_c: float = Field(description="sensed temperature where charge derating starts")
    derate_end_c: float = Field(description="sensed temperature where charge current reaches zero")
    derate_on: Literal["sensed", "observer"] = Field(
        "sensed", description="hotspot signal for derating: hottest NTC, or on-board thermal observer")
    observer_h_error: float = Field(
        0.0, description="relative error in the observer's cooling model (+ = assumes better cooling than real)")


class Mechanical(BaseModel):
    holder_busbar_mass_per_cell_kg: float
    enclosure_mass_kg: float
    packing_fraction: float = 0.785
    volume_overhead_factor: float = 1.4


class Costs(BaseModel):
    holder_busbar_per_cell_inr: float
    assembly_per_cell_inr: float
    enclosure_inr: float


class Variation(BaseModel):
    capacity_sigma: float = 0.015
    r0_sigma: float = 0.04
    seed: int = 0


class Design(BaseModel):
    id: str
    name: str
    description: str = ""
    cell: Cell
    topology: Topology
    interconnect: Interconnect
    cooling: Cooling
    sensing: Sensing
    bms: Bms
    protection: Protection
    control: Control
    mechanical: Mechanical
    costs: Costs
    variation: Variation = Variation()
    assumptions: list[Assumption] = Field(default_factory=list)

    @property
    def n_cells(self) -> int:
        return self.topology.series * self.topology.parallel

    @property
    def capacity_ah(self) -> float:
        return self.topology.parallel * self.cell.capacity_ah

    def all_assumptions(self) -> list[Assumption]:
        return self.cell.assumptions + self.assumptions


class Requirement(BaseModel):
    id: str
    text: str
    metric: str
    min: float | None = None
    max: float | None = None
    unit: str = ""
    priority: Literal["must", "should"] = "must"


class Scenario(BaseModel):
    type: Literal["charge", "drive", "current"]
    start_soc: float
    max_time_s: int = 14400
    after: str | None = Field(
        None, description="start from the end state of this scenario (SOC, temperatures); start_soc is then ignored")
    profile: list[tuple[float, float]] = Field(
        default_factory=list,
        description="repeating [duration_s, value] segments: power W (drive) or current A, + = discharge (current)")


class Study(BaseModel):
    """Application context shared by all design options being compared."""

    application: str
    ambient_c: float
    scenarios: dict[str, Scenario]
    requirements: list[Requirement]
    score_weights: dict[str, float] = Field(
        default_factory=dict, description="metric -> weight; sign gives direction (+ higher is better)"
    )
