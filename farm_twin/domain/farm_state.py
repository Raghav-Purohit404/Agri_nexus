"""
FILE: farm_twin/domain/farm_state.py
PURPOSE: THE canonical FarmState. FarmState(t) -> Intervention -> FarmState(t+1).

IMPLEMENT:
    class PlotState: plot (static), soil: SoilState, crop: CropState|None, solar: PVConfig|None, microclimate_adjust (agrivoltaic ground radiation fraction,
        wind factor, dT), land_use, last_observation_dates: dict[var, date]
    class PropertyState: water: WaterState, infra: InfraState, finance: FinancialState
    class FarmState: date, property: PropertyState, plots: dict[PlotId, PlotState], weather_today: WeatherDay(Quantified fields),
        meta: {state_id, parent_state_id, sim_run_id, parameter_set_ids: dict[model, id], created_by}
        methods: snapshot() (deep, immutable-by-convention copy), diff(other) -> list of (path, old, new), hash()
        validate() -> checks invariants: area partition sums to property area (+/-0.5%), theta in [theta_dry, theta_sat], CC in [0,1], carbon pools >= 0,
                      no plot has two incompatible land uses.
    Persist each daily state ONLY as a delta against the previous state (state_delta table) plus periodic full snapshots (monthly); this keeps 10-year x N-scenario runs affordable.
TESTS: snapshot/diff/hash; validate() catches negative carbon pool; delta replay reproduces the state exactly.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, TypeAdapter

from farm_twin.core.ids import input_hash, new_id
from farm_twin.core.provenance import Quantified
from farm_twin.domain.crop_state import CropState
from farm_twin.domain.financial_state import FinancialState
from farm_twin.domain.infrastructure_state import InfraState
from farm_twin.domain.property_plot import LandUse, Plot, Property
from farm_twin.domain.soil_state import SoilState
from farm_twin.domain.solar_state import PVConfig
from farm_twin.domain.water_state import WaterState
from farm_twin.domain.crop_state import CropStatus
from farm_twin.domain.interventions import ChangeLandUse, Harvest, InstallPV, Intervention, Plant
from farm_twin.domain.solar_state import PVKind


class PropertyState(BaseModel):
    water: WaterState = Field(default_factory=lambda: WaterState())
    infra: InfraState = Field(default_factory=lambda: InfraState())
    finance: FinancialState = Field(default_factory=lambda: FinancialState())


class PlotState(BaseModel):
    plot: Plot
    soil: SoilState
    crop: CropState | None = None
    solar: PVConfig | None = None
    microclimate_adjust: dict[str, float] = Field(default_factory=dict)
    land_use: LandUse | None = None
    last_observation_dates: dict[str, date] = Field(default_factory=dict)


class WeatherDay(BaseModel):
    date: date
    values: dict[str, Quantified[float]] = Field(default_factory=dict)


class StateMeta(BaseModel):
    state_id: str = Field(default_factory=lambda: new_id("state"))
    parent_state_id: str | None = None
    sim_run_id: str | None = None
    parameter_set_ids: dict[str, str] = Field(default_factory=dict)
    created_by: str = "system"


class FarmState(BaseModel):
    date: date
    property: PropertyState
    plots: dict[str, PlotState]
    property_static: Property | None = None
    weather_today: WeatherDay | None = None
    meta: StateMeta = Field(default_factory=StateMeta)

    def snapshot(self) -> "FarmState":
        return self.model_copy(deep=True)

    def diff(self, other: "FarmState") -> list[tuple[str, Any, Any]]:
        left = self.model_dump(mode="python")
        right = other.model_dump(mode="python")
        changes: list[tuple[str, Any, Any]] = []

        def walk(a: Any, b: Any, path: str) -> None:
            if isinstance(a, dict) and isinstance(b, dict):
                for key in sorted(set(a) | set(b)):
                    walk(a.get(key), b.get(key), f"{path}.{key}" if path else str(key))
            elif a != b:
                changes.append((path, a, b))

        walk(left, right, "")
        return changes

    def hash(self) -> str:
        return input_hash(self.model_dump(mode="json"))

    def validate_invariants(self) -> None:
        if self.property_static and self.property_static.area_m2 is not None:
            total = sum(float(p.plot.area_m2) for p in self.plots.values())
            if total > self.property_static.area_m2 * 1.005:
                raise ValueError("plot areas exceed property area by more than 0.5%")
        for plot_id, state in self.plots.items():
            if state.crop and not 0 <= state.crop.canopy_cover <= 1:
                raise ValueError(f"plot {plot_id}: canopy cover outside [0,1]")
            for layer in state.soil.layers:
                for name in ("theta", "theta_wp", "theta_fc", "theta_sat", "theta_dry"):
                    q = getattr(layer, name)
                    if q and q.value is not None and not 0 <= q.value <= 1:
                        raise ValueError(f"plot {plot_id}: {name} outside [0,1]")
                if any(q.value is not None and q.value < 0 for q in layer.rothc_pools_tC_ha.values()):
                    raise ValueError(f"plot {plot_id}: negative soil carbon pool")

    def apply_intervention(self, value: Intervention | dict[str, Any]) -> "FarmState":
        """Apply state-owning interventions; dynamic flux interventions are delegated to model kernels."""
        adapter = TypeAdapter(Intervention)
        action = adapter.validate_python(value)
        if action.plot_id is None or action.plot_id not in self.plots:
            raise ValueError("intervention must reference an existing plot")
        plot_state = self.plots[action.plot_id].model_copy(deep=True)
        plots = dict(self.plots)
        if isinstance(action, Plant):
            if plot_state.land_use in {LandUse.PV_GROUND, LandUse.WATER_STORAGE, LandUse.STRUCTURE}:
                raise ValueError(f"cannot plant on {plot_state.land_use}")
            if plot_state.crop is not None and plot_state.crop.status not in {CropStatus.FALLOW, CropStatus.HARVESTED}:
                raise ValueError("cannot plant while a crop is active")
            if action.date is None:
                raise ValueError("planting date is required")
            crop = CropState(crop_id=action.crop, variety=action.variety, planting_date=action.date, status=CropStatus.PLANTED)
            plot_state = plot_state.model_copy(update={"crop": crop})
        elif isinstance(action, Harvest):
            if plot_state.crop is None or plot_state.crop.status in {CropStatus.FALLOW, CropStatus.HARVESTED}:
                raise ValueError("plot has no active crop to harvest")
            crop = plot_state.crop.model_copy(update={"status": CropStatus.HARVESTED})
            plot_state = plot_state.model_copy(update={"crop": crop})
        elif isinstance(action, ChangeLandUse):
            if action.new_use not in plot_state.plot.eligible_uses:
                raise ValueError(f"land use {action.new_use.value} is not eligible for this plot")
            static_plot = plot_state.plot.model_copy(update={"land_use_current": action.new_use})
            plot_state = plot_state.model_copy(update={"plot": static_plot, "land_use": action.new_use})
        elif isinstance(action, InstallPV):
            config = action.config if isinstance(action.config, PVConfig) else PVConfig.model_validate(action.config)
            use = LandUse.AGRIVOLTAIC if config.kind == PVKind.ELEVATED_AGRIVOLTAIC_FIXED else LandUse.PV_GROUND
            if use not in plot_state.plot.eligible_uses:
                raise ValueError(f"land use {use.value} is not eligible for this plot")
            static_plot = plot_state.plot.model_copy(update={"land_use_current": use})
            plot_state = plot_state.model_copy(update={"plot": static_plot, "land_use": use, "solar": config})
        else:
            raise NotImplementedError(f"{action.kind} changes dynamic fluxes and must be consumed by a registered model")
        plots[action.plot_id] = plot_state
        return self.model_copy(update={"plots": plots}, deep=True)
