"""
FILE: farm_twin/domain/interventions.py
PURPOSE: Typed Interventions - the ONLY way state is changed by decisions.

IMPLEMENT (pydantic discriminated union on `kind`):
    Plant(plot, crop, variety, date, population, method {SOW, TRANSPLANT}), Harvest(plot, date), Irrigate(plot, date, gross_mm, method, source),
    IrrigationPolicy(plot, mode {FIXED_SCHEDULE, SOIL_MOISTURE_THRESHOLD, ET_REPLACEMENT, RAINFED}, smt_pct_taw per growth stage, max_depth_mm, interval_days, season_cap_mm),
    ApplyFertiliser(plot, date, product, kg_product_ha, N/P2O5/K2O fractions, method), ApplyOrganic(plot, date, kind {FYM, COMPOST, CROP_RESIDUE, GREEN_MANURE},
        t_dry_matter_ha, c_fraction, n_fraction), ApplyAmendment(plot, date, product {GYPSUM, SULPHUR, LIME}, kg_ha),
    ChangeLandUse(plot, date, new_use), InstallPV(plot, PVConfig, date), InstallInfra(asset), Mulch(plot, pct_cover, dates), SetIrrigationSystem(...), TillageEvent(plot, date, depth_m)
    class InterventionPlan: list[Intervention] ordered by date; validate(farm_state) (e.g. cannot Plant on a PV_GROUND plot; cannot exceed budget)
    Every intervention has `proposed_by` {USER, OPTIMIZER, AGENT:<name>}, `approval_id|None`, `status {PROPOSED, APPROVED, EXECUTED, REJECTED}`.
RULE: only status==APPROVED (or user-created) interventions may be executed against ACTUAL records; simulation may run PROPOSED plans as hypotheticals.
"""

from __future__ import annotations

from datetime import date as Date
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter, model_validator

from farm_twin.domain.property_plot import LandUse


class ProposedBy(str, Enum):
    USER = "USER"
    OPTIMIZER = "OPTIMIZER"
    AGENT = "AGENT"


class InterventionStatus(str, Enum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"


class InterventionBase(BaseModel):
    kind: str
    plot_id: str | None = None
    date: Date | None = None
    proposed_by: str = "USER"
    approval_id: str | None = None
    status: InterventionStatus = InterventionStatus.PROPOSED


class Plant(InterventionBase):
    kind: Literal["Plant"] = "Plant"
    crop: str
    variety: str | None = None
    population: float | None = None
    method: Literal["SOW", "TRANSPLANT"] = "SOW"


class Harvest(InterventionBase):
    kind: Literal["Harvest"] = "Harvest"


class Irrigate(InterventionBase):
    kind: Literal["Irrigate"] = "Irrigate"
    gross_mm: float
    method: str
    source: str


class ApplyFertiliser(InterventionBase):
    kind: Literal["ApplyFertiliser"] = "ApplyFertiliser"
    product: str
    kg_product_ha: float
    n_fraction: float = 0
    p2o5_fraction: float = 0
    k2o_fraction: float = 0
    method: str | None = None


class ApplyOrganic(InterventionBase):
    kind: Literal["ApplyOrganic"] = "ApplyOrganic"
    organic_kind: Literal["FYM", "COMPOST", "CROP_RESIDUE", "GREEN_MANURE"]
    t_dry_matter_ha: float
    c_fraction: float
    n_fraction: float


class ApplyAmendment(InterventionBase):
    kind: Literal["ApplyAmendment"] = "ApplyAmendment"
    product: Literal["GYPSUM", "SULPHUR", "LIME"]
    kg_ha: float


class ChangeLandUse(InterventionBase):
    kind: Literal["ChangeLandUse"] = "ChangeLandUse"
    new_use: LandUse


class InstallPV(InterventionBase):
    kind: Literal["InstallPV"] = "InstallPV"
    config: dict


class Mulch(InterventionBase):
    kind: Literal["Mulch"] = "Mulch"
    pct_cover: float


class TillageEvent(InterventionBase):
    kind: Literal["TillageEvent"] = "TillageEvent"
    depth_m: float


class IrrigationPolicy(InterventionBase):
    kind: Literal["IrrigationPolicy"] = "IrrigationPolicy"
    mode: Literal["FIXED_SCHEDULE", "SOIL_MOISTURE_THRESHOLD", "ET_REPLACEMENT", "RAINFED"]
    smt_pct_taw: dict[str, float] = Field(default_factory=dict)
    max_depth_mm: float | None = None
    interval_days: int | None = None
    season_cap_mm: float | None = None


Intervention = Annotated[
    Union[
        Plant,
        Harvest,
        Irrigate,
        ApplyFertiliser,
        ApplyOrganic,
        ApplyAmendment,
        ChangeLandUse,
        InstallPV,
        Mulch,
        TillageEvent,
        IrrigationPolicy,
    ],
    Field(discriminator="kind"),
]
_adapter = TypeAdapter(Intervention)


class InterventionPlan(BaseModel):
    interventions: list[Intervention] = Field(default_factory=list)

    @model_validator(mode="after")
    def order(self) -> "InterventionPlan":
        dated = [i.date for i in self.interventions if i.date]
        if dated != sorted(dated):
            raise ValueError("interventions must be ordered by date")
        return self

    def validate_for_state(self, farm_state: object) -> list[str]:
        issues: list[str] = []
        plots = getattr(farm_state, "plots", {})
        for intervention in self.interventions:
            if intervention.plot_id not in plots and intervention.plot_id is not None:
                issues.append(f"unknown plot: {intervention.plot_id}")
            if isinstance(intervention, Plant) and intervention.plot_id in plots:
                if plots[intervention.plot_id].land_use == LandUse.PV_GROUND:
                    issues.append("cannot plant on PV_GROUND plot")
        return issues

    def executable(self, *, hypothetical: bool = False) -> list[Intervention]:
        if hypothetical:
            return self.interventions
        return [i for i in self.interventions if i.status in {InterventionStatus.APPROVED} or i.proposed_by == "USER"]
