"""Pydantic v2 domain schemas for VoltTwin.

Datasheet specs (cell, cooling, busbar, protection) are model inputs and each carries a `source` string —
every number must state where it came from. `ModuleDesignInput` references specs by id;
`ModuleSimulationResult` field names are the metric keys that requirements point at.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Evidence = Literal["datasheet", "assumption", "calculated", "estimated", "simulated", "measured"]
Status = Literal["PASS", "FAIL"]
Verdict = Literal["OPTIMAL", "ACCEPTABLE", "REJECTED", "UNSAFE"]  # ACCEPTABLE = eligible but not the top pick


class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    source: str = Field(min_length=1, description="where the numbers come from (datasheet, handbook, assumption)")


class CellSpec(_Spec):
    chemistry: Literal["NMC", "LFP"]
    form_factor: str
    v_nom_v: float = Field(gt=0)
    v_max_v: float = Field(gt=0)
    v_min_v: float = Field(gt=0)
    capacity_ah: float = Field(gt=0)
    r0_ohm: float = Field(gt=0, description="DC internal resistance at 25 C, beginning of life")
    mass_kg: float = Field(gt=0)
    diameter_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)
    cp_j_kgk: float = Field(gt=0)
    max_charge_c: float = Field(gt=0)
    max_discharge_c: float = Field(gt=0)
    t_charge_max_c: float
    t_discharge_max_c: float
    cost_usd: float = Field(ge=0)
    pybamm_parameter_set: str

    @model_validator(mode="after")
    def _voltage_window(self) -> "CellSpec":
        if not self.v_min_v < self.v_nom_v < self.v_max_v:
            raise ValueError(f"{self.id}: need v_min < v_nom < v_max")
        return self

    @property
    def energy_wh(self) -> float:
        return self.v_nom_v * self.capacity_ah

    @property
    def volume_l(self) -> float:
        r_m, h_m = self.diameter_mm / 2000, self.height_mm / 1000
        return 3.141592653589793 * r_m**2 * h_m * 1000


class CoolingSpec(_Spec):
    kind: Literal["passive", "forced_air", "conduction_pcm"]
    r_th_k_w: float = Field(gt=0, description="lumped pack-to-ambient thermal resistance")
    q_dissipation_w: float = Field(gt=0, description="heat rejected at 10 K pack-to-ambient difference")
    fan_power_w: float = Field(ge=0)
    pcm_mass_kg: float = Field(ge=0)
    pcm_latent_j_kg: float = Field(ge=0)
    pcm_melt_c: float | None = None
    mass_kg: float = Field(ge=0)
    volume_l: float = Field(ge=0)
    cost_usd: float = Field(ge=0)

    @model_validator(mode="after")
    def _pcm_consistent(self) -> "CoolingSpec":
        has_pcm = self.pcm_mass_kg > 0
        if has_pcm != (self.pcm_melt_c is not None) or has_pcm != (self.pcm_latent_j_kg > 0):
            raise ValueError(f"{self.id}: PCM mass, latent heat and melt point must be set together")
        return self


class BusbarSpec(_Spec):
    material: Literal["Ni", "Cu"]
    thickness_mm: float = Field(gt=0)
    width_mm: float = Field(gt=0)
    resistivity_ohm_m: float = Field(gt=0)
    link_length_mm: float = Field(gt=0)
    ampacity_a: float = Field(gt=0)
    mass_per_cell_kg: float = Field(ge=0)
    cost_per_cell_usd: float = Field(ge=0)

    @property
    def link_resistance_ohm(self) -> float:
        area_m2 = self.thickness_mm * self.width_mm * 1e-6
        return self.resistivity_ohm_m * self.link_length_mm * 1e-3 / area_m2


class ProtectionSpec(_Spec):
    kind: Literal["ntc", "fuse", "pyro_fuse", "bms"]
    rating_a: float | None = Field(None, gt=0)
    ntc_channels: int | None = Field(None, gt=0)
    fan_pwm: bool = False
    active_balancing: bool = False
    thermal_aware_charging: bool = False
    mass_kg: float = Field(ge=0)
    cost_usd: float = Field(ge=0)

    @model_validator(mode="after")
    def _kind_fields(self) -> "ProtectionSpec":
        if self.kind in ("fuse", "pyro_fuse", "bms") and self.rating_a is None:
            raise ValueError(f"{self.id}: {self.kind} needs rating_a")
        if self.kind == "bms" and self.ntc_channels is None:
            raise ValueError(f"{self.id}: bms needs ntc_channels")
        return self


class HardRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    text: str
    metric: str = Field(description="field name in ModuleSimulationResult")
    min: float | None = None
    max: float | None = None
    unit: str
    cutoff: str

    @model_validator(mode="after")
    def _has_limit(self) -> "HardRequirement":
        if self.min is None and self.max is None:
            raise ValueError(f"{self.id}: needs min and/or max")
        return self

    def status(self, value: float) -> Status:
        ok = (self.min is None or value >= self.min) and (self.max is None or value <= self.max)
        return "PASS" if ok else "FAIL"


class ModuleDesignInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    cell_id: str
    n_series: int = Field(gt=0)
    n_parallel: int = Field(gt=0)
    cooling_id: str
    busbar_id: str
    n_ntc: int = Field(ge=0)
    fuse_id: str
    bms_id: str
    usable_dod: float = Field(gt=0, le=1, description="fraction of nominal capacity in the usable SoC window")
    charge_c_rate: float = Field(gt=0)
    ambient_c: float = 40.0
    source: str = Field(min_length=1)

    @property
    def n_cells(self) -> int:
        return self.n_series * self.n_parallel


class ModuleSimulationResult(BaseModel):
    design_id: str
    engine: Literal["pybamm", "surrogate"]
    v_nom_v: float
    v_min_v: float
    v_max_v: float
    n_cells: int
    capacity_ah: float
    nominal_energy_kwh: float
    usable_energy_kwh: float
    r_pack_ohm: float
    r_eff_ratio_vs_datasheet: float = Field(description="cell resistance used / datasheet R0 (1 for surrogate)")
    peak_discharge_a: float
    busbar_strip_current_a: float
    t_charge_start_c: float = Field(description="hottest-cell temperature at plug-in (after the ride)")
    t_peak_c: float = Field(description="hottest-cell peak over ride + charge at the design rate, no derating")
    t_peak_derated_c: float = Field(description="hottest-cell peak with BMS derating active")
    charge_time_10_80_min: float = Field(description="10-80 % at the design rate, no derating")
    charge_time_derated_min: float = Field(description="10-80 % with BMS derating = real turnaround")
    charge_complete: bool = True
    heat_gen_w: float = Field(description="mean heat generated during the charge")
    heat_cells_w: float
    heat_reversible_w: float
    heat_busbar_w: float
    heat_reject_w: float = Field(description="mean heat rejected to ambient during the charge")
    heat_pcm_w: float = Field(description="mean heat absorbed as PCM latent heat during the charge")
    mass_kg: float
    volume_l: float
    bom_cost_usd: float
    requirement_status: dict[str, Status] = Field(default_factory=dict)
    verdict: Verdict | None = None
    notes: list[str] = Field(default_factory=list)


class TraceabilityRecord(BaseModel):
    requirement_id: str
    datasheet_parameters: list[str] = Field(description="'<spec id>.<field>' inputs the metric depends on")
    physics_model: str
    assumptions: list[str] = Field(default_factory=list, description="ids in src.physics.assumptions.ASSUMPTIONS")
    simulated_metric: str
    value: float
    limit: str
    status: Status
    evidence: Evidence
    validation_reference: str
