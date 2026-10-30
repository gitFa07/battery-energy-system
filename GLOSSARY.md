# PackForge

A workbench for designing small battery systems from cell to pack: configure design options, simulate them
against an application's requirements, and recommend one with its risks stated.

## Hardware

**Pack**:
The complete battery of the application — every cell, interconnect, sensor, BMS and enclosure. For the e-scooter
study the 13S10P battery is the pack, not a module of one.
_Avoid_: Module (unless it is genuinely one building block of a larger pack), battery system

**Parallel group**:
Cells wired in parallel that share one terminal voltage; groups are then connected in series.
_Avoid_: Series group, cell block, row

**Hotspot**:
The hottest cell in the pack at a given moment, wherever it is.
_Avoid_: Max temp (ambiguous between true and sensed)

**Blind spot**:
How far the hotspot's true temperature exceeds the temperature the BMS acts on.
_Avoid_: Sensor error, sensor offset

## Control

**Derating**:
The BMS reducing charge current as the temperature it acts on rises through a set window.
_Avoid_: Throttling, current limiting

**Thermal hold**:
Time after plug-in when the charger delivers no current because the pack is too hot to accept charge; it ends
when derating releases. A hold is not a protection trip.
_Avoid_: Cooldown, OT trip, charge inhibit

**Charge time**:
Plug-in to 80 % state of charge, including any thermal hold — what the rider experiences. The headline charging
figure.
_Avoid_: Charging duration, time to charge

**10–80 % charge time**:
Time from 10 % to 80 % state of charge, excluding any hold before 10 %. Secondary figure for comparison with
industry ratings only.
_Avoid_: Fast-charge time, charge time (that term means plug-in to 80 %)

## Design process

**Study**:
One application (use case, ambient conditions, scenarios, requirements) against which design options are compared.
_Avoid_: Project, case, scenario (a scenario is one charge or drive event within a study)

**Design option**:
One candidate configuration of a pack within a study, described by how it differs from the baseline.
_Avoid_: Variant, config, alternative

**Baseline**:
The starting design option that every other option is compared against.
_Avoid_: Reference design, default

**Requirement**:
A limit on one result, either _must_ (violating it disqualifies the option) or _should_ (violating it is a
stated risk).
_Avoid_: Spec, constraint, target

**Evidence level**:
How a number was obtained — datasheet, assumption, calculated, estimated, simulated or measured — in increasing
order of trust. A number measured on a proxy cell is "measured (proxy)".
_Avoid_: Confidence, source type

**Proxy cell**:
A real, publicly tested cell whose measured behaviour stands in for a generic cell of the same chemistry and
format class.
_Avoid_: Reference cell, equivalent cell

**Hold-out check**:
A comparison of model predictions against measured data that was not used to fit the model.
_Avoid_: Validation (too broad), test set

**Test rig**:
The chamber, holder and wiring a cell was measured in. Its cooling and heat capacity are fitted alongside the cell
but describe the rig, so they never carry over to a pack.
_Avoid_: Setup, bench (when the rig's own properties are meant)

**Unmodelled heat**:
Heat the real cells generate beyond what the cell model predicts. Studied by re-running every design with a heat
multiple the BMS is not told about; a recommendation that survives it is robust.
_Avoid_: Heat error, safety factor

**Retrofit**:
A design option that changes only BMS settings of packs already built, so it costs no hardware.
_Avoid_: Upgrade, software option, firmware fix (fine in speech, but the option is the retrofit)
