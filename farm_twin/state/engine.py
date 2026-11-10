"""
FILE: farm_twin/state/engine.py
PURPOSE: FarmStateEngine - runs FarmState(t) + InterventionPlan + weather -> FarmState(t+1...T). The ONLY orchestrator of models; everything else (agents, optimiser, API) calls it.

DESIGN: operator splitting with a fixed daily order (deterministic, mass-conserving). For each day d and each plot p (plots are independent except via shared water/finance):
   1. forcing(d): weather_d (scenario draw), microclimate factors for p (agrivoltaic/ground_radiation, precomputed per day), PV config.
   2. apply interventions scheduled on d (plant, irrigate, fertilise, amend, land-use change) -> validate -> mutate a COPY of the plot state.
   3. ET0 for the plot (reference_et with microclimate scales).
   4. soil water + crop daily step (crop engine owns the water balance call) -> fluxes.
   5. salinity step (uses water fluxes), nutrients step (uses fluxes + crop demand) -> stress factors for NEXT day (one-day lag is deliberate, documented).
   6. solar hourly for the day (PV plots) - may be batched weekly for speed since PV state is not feedback-coupled to crops except via shade (precomputed).
   7. property-level: water-source ledger (sum plot irrigation demand vs availability; unmet demand reduces applied irrigation proportionally by priority list), costs/revenue events appended to cashflow ledger.
   8. month end: carbon step (RothC) using aggregated residue inputs, monthly T and moisture; recompute pedotransfer-dependent soil properties from updated OM annually.
   9. season end/harvest: yield, residue, crop history record; roll CropState to FALLOW.
   10. checks: MassBalanceError on water/salt/N/C ledgers; FarmState.validate(); emit state delta.
COUPLING GRAPH (state/coupling.py): declare which model outputs feed which inputs; engine topologically sorts; cyclic dependencies (water<->salinity<->crop) are resolved by the explicit one-day lag. Capability negotiation (models/base.py) decides which processes are active.
PARALLELISM: scenario axis vectorised inside models; plot axis via joblib/ProcessPool (no shared mutable state); 10 yr x 50 scenarios x 5 plots target < 5 min on a laptop CPU (no GPU required).
PERSISTENCE: write sim_run row first; store KPIs and quantile paths in `prediction`; state deltas in `state_delta`; failures stored with traceback hash; engine is idempotent given (input_hash, rng_seed).
APIS: run(scenario) -> ScenarioResult ; run_one(plot, start, end, weather, plan) ; step(state, forcing, actions) -> (state, fluxes) ; what_if(base_state, plan_variant) (copy-on-write; uses common random numbers) ; hindcast(plot, start, end) which runs from the last MEASURED state with ACTUAL weather and ACTUAL interventions - the basis of calibration & validation.
UNCERTAINTY PROPAGATION: engine accepts `param_draws` (from calibration posteriors) and `weather_draws`; outputs carry ensembles; engine never returns a single number as 'the answer' - returns summary stats + samples.
TESTS: 1-plot fallow year (only evaporation) mass balance; two-plot independence; reproducibility; fixture regression against crop-engine golden; hindcast uses actual not planned interventions.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from copy import deepcopy
from hashlib import sha256
import json
from typing import Any, Callable, Mapping

from farm_twin.state.coupling import DEFAULT_EDGES, topological_order
from farm_twin.core.errors import MassBalanceError


@dataclass(frozen=True)
class DailyForcing:
    date: str
    weather: Mapping[str, Any]
    actual_interventions: tuple[Mapping[str, Any], ...] = ()
    planned_interventions: tuple[Mapping[str, Any], ...] = ()
    mode: str = "forecast"


@dataclass(frozen=True)
class StateDelta:
    before_hash: str
    after_hash: str
    date: str


@dataclass
class ScenarioResult:
    states: list[Any] = field(default_factory=list)
    fluxes: list[Mapping[str, Any]] = field(default_factory=list)
    deltas: list[StateDelta] = field(default_factory=list)
    seed: int = 0
    input_hash: str = ""


def _hash(state: Any) -> str:
    obj = state.model_dump(mode="json") if hasattr(state, "model_dump") else state
    return sha256(json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


class FarmStateEngine:
    """Deterministic operator wrapper; concrete model functions are injected by composition."""

    def __init__(self, models: Mapping[str, Callable[..., tuple[Any, Mapping[str, Any]]]], edges=DEFAULT_EDGES) -> None:
        self.models = dict(models)
        self.edges = tuple(edges)
        self.order = topological_order(self.edges, self.models.keys())

    def step(self, state: Any, forcing: DailyForcing, actions: tuple[Mapping[str, Any], ...] | None = None):
        before = _hash(state)
        current = deepcopy(state)
        fluxes = {}
        use_actions = (
            actions
            if actions is not None
            else (forcing.actual_interventions if forcing.mode == "hindcast" else forcing.planned_interventions)
        )
        dynamic_actions: list[Mapping[str, Any]] = []
        for action in use_actions:
            apply = getattr(current, "apply_intervention", None)
            if apply is None:
                raise TypeError("state must implement apply_intervention for non-empty action plans")
            action_data = action.model_dump(mode="json") if hasattr(action, "model_dump") else dict(action)
            if forcing.mode == "hindcast" and action_data.get("status") != "EXECUTED":
                raise ValueError("hindcast interventions must be recorded as EXECUTED actual interventions")
            try:
                current = apply(action_data)
            except NotImplementedError:
                dynamic_actions.append(action_data)
        effective_forcing = (
            replace(forcing, actual_interventions=tuple(dynamic_actions))
            if forcing.mode == "hindcast"
            else replace(forcing, planned_interventions=tuple(dynamic_actions))
        )
        for name in self.order:
            current, out = self.models[name](current, effective_forcing, fluxes)
            fluxes[name] = dict(out)
            ledger = out.get("mass_balance")
            if ledger is not None:
                inputs = float(ledger["inputs"])
                outputs = float(ledger["outputs"])
                storage_change = float(ledger["storage_change"])
                residual = inputs - outputs - storage_change
                tolerance = float(ledger.get("tolerance", 1e-6))
                if abs(residual) > tolerance:
                    raise MassBalanceError(
                        f"{name} ledger residual {residual:g} exceeds tolerance {tolerance:g}",
                        context={"model": name, "residual": residual, "tolerance": tolerance},
                    )
        validate = getattr(current, "validate_invariants", None)
        if validate is not None:
            validate()
        if hasattr(current, "meta") and hasattr(current, "model_copy"):
            from uuid import NAMESPACE_URL, uuid5

            previous_state_id = current.meta.state_id
            deterministic_id = f"state_{uuid5(NAMESPACE_URL, previous_state_id + forcing.date + _hash(current))}"
            next_meta = current.meta.model_copy(
                update={"state_id": deterministic_id, "parent_state_id": previous_state_id}
            )
            current = current.model_copy(update={"meta": next_meta}, deep=True)
        if hasattr(current, "model_copy") and hasattr(current, "date"):
            from datetime import date

            try:
                current = current.model_copy(update={"date": date.fromisoformat(forcing.date)}, deep=True)
            except ValueError as exc:
                raise ValueError(f"forcing date must be ISO-8601: {forcing.date}") from exc
        return current, fluxes, StateDelta(before, _hash(current), forcing.date)

    def run_one(self, state: Any, forcings: list[DailyForcing], *, seed: int = 0) -> ScenarioResult:
        result = ScenarioResult(
            seed=seed, input_hash=sha256((_hash(state) + repr(forcings) + str(seed)).encode()).hexdigest()
        )
        current = deepcopy(state)
        for forcing in forcings:
            current, flux, delta = self.step(current, forcing)
            result.states.append(deepcopy(current))
            result.fluxes.append(flux)
            result.deltas.append(delta)
        return result

    def hindcast(self, state: Any, forcings: list[DailyForcing], *, seed: int = 0) -> ScenarioResult:
        actual = [DailyForcing(f.date, f.weather, f.actual_interventions, (), "hindcast") for f in forcings]
        return self.run_one(state, actual, seed=seed)

    def run(self, scenario: Any) -> ScenarioResult:
        """Run an explicitly materialized scenario contract; no implicit data/provider calls."""
        initial_state = getattr(scenario, "initial_state", None)
        forcings = getattr(scenario, "forcings", None)
        if initial_state is None or forcings is None:
            raise ValueError("scenario must provide initial_state and materialized forcings")
        return self.run_one(initial_state, list(forcings), seed=int(getattr(scenario, "seed", 0)))

    def what_if(self, base_state: Any, forcings: list[DailyForcing], plan_variant: list[tuple[Mapping[str, Any], ...]], *, seed: int) -> ScenarioResult:
        """Evaluate a plan variant using supplied common-random-number forcings and a copy of base state."""
        if len(forcings) != len(plan_variant):
            raise ValueError("plan variant must contain an action list for every forcing day")
        variant = [
            DailyForcing(f.date, f.weather, f.actual_interventions, tuple(actions), "forecast")
            for f, actions in zip(forcings, plan_variant)
        ]
        return self.run_one(deepcopy(base_state), variant, seed=seed)
