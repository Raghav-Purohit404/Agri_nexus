"""
FILE: farm_twin/agents/tools/registry.py
PURPOSE: Typed tool layer between LLM agents and the deterministic scientific core. Agents NEVER compute science themselves; they call tools.

IMPLEMENT: @tool-style registry where each tool = (name, pydantic input schema, pydantic output schema, handler, side_effect {NONE, READ_EXTERNAL, WRITE_STATE, WRITE_RECOMMENDATION, EXTERNAL_ACTION}, requires_approval: bool, timeout_s, idempotent: bool, allowed_agents: set[str]).
 Wrapper behaviour for every call: (1) validate args with pydantic (reject unknown fields); (2) check allowed_agents; (3) approval gate for side_effect >= WRITE_STATE where requires_approval (raises ApprovalRequiredError -> graph interrupt); (4) execute with timeout & retry on transient errors only; (5) catch FarmTwinError -> return {ok:false, error:{code,message,context}} (never raise into the LLM loop); (6) write tool_call row (args, result hash, duration); (7) create EvidenceItem from output; (8) truncate large outputs to a summary + artifact reference (arrays are never pasted into prompts).
 TOOL CATALOGUE (name: purpose [side effect]):
   property.create/update_plot, plot.import_geometry [WRITE_STATE, approval=no (user supplied)]
   data.upload_soil_report, data.parse_soil_report, data.confirm_fields [WRITE_STATE]
   data.fetch_weather(lon,lat,range), data.fetch_forecast, data.fetch_soil_prior, data.fetch_prices, data.fetch_satellite_stats [READ_EXTERNAL]
   quality.run_checks(plot|property), quality.completeness(plot, model) [NONE]
   soil.estimate_properties(plot) (pedotransfer, returns ESTIMATED with uncertainty), soil.salinity_assess(plot), soil.amendment_plan(plot), soil.carbon_projection(plot, scenario)
   crop.simulate_season(plot, crop, planting_date, irrigation_policy, n_weather), crop.compare_crops(plot, crop_list), crop.irrigation_schedule(plot, horizon_days)
   water.balance(property, scenario), water.storage_sizing
   solar.estimate_energy(plot, pvconfig), solar.size_layout(plot, constraints)
   agrivoltaic.evaluate(plot, pv_config, crop) (returns RY, LER, flags unvalidated)
   finance.cashflow(scenario), finance.compare(scenario_ids)
   uncertainty.run_ensemble(scenario, n), uncertainty.sensitivity(scenario)
   optimize.allocate(property, objectives, constraints, risk_lambda), optimize.pareto(...)
   voi.rank_measurements(property)
   calibration.run(plot|farm, model), calibration.status, calibration.history [promotion done ONLY by the gate; tool cannot override it]
   loop.record_recommendation [WRITE_RECOMMENDATION], loop.record_outcome [WRITE_STATE], loop.error_report
   report.build(scenario_ids, audience) -> artifact [NONE]
   approval.request(recommendation_id) [creates ApprovalRequest; human decides]
 TESTS: schema rejection, allowed_agents enforcement, approval gating, error-to-dict conversion, large-output truncation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from hashlib import sha256
import json
import time
from typing import Any, Callable, Type
from pydantic import BaseModel
from farm_twin.core.errors import FarmTwinError, ApprovalRequiredError


class SideEffect(IntEnum):
    NONE = 0
    READ_EXTERNAL = 1
    WRITE_RECOMMENDATION = 2
    WRITE_STATE = 3
    EXTERNAL_ACTION = 4


@dataclass(frozen=True)
class ToolSpec:
    name: str
    input_model: Type[BaseModel]
    output_model: Type[BaseModel]
    handler: Callable[[BaseModel], Any]
    side_effect: SideEffect = SideEffect.NONE
    requires_approval: bool = False
    timeout_s: float = 30.0
    idempotent: bool = True
    allowed_agents: frozenset[str] = frozenset()


class ToolRegistry:
    def __init__(
        self,
        approval_validator: Callable[[str, str, dict[str, Any]], bool] | None = None,
        artifact_store: Callable[[dict[str, Any]], str] | None = None,
        max_inline_bytes: int = 32_000,
    ) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self.calls = []
        self.approval_validator = approval_validator
        self.artifact_store = artifact_store
        self.max_inline_bytes = max_inline_bytes

    def register(self, tool: ToolSpec) -> None:
        if tool.name in self._tools:
            raise ValueError(f"duplicate tool {tool.name}")
        self._tools[tool.name] = tool

    def call(self, name: str, args: dict[str, Any], agent: str, approval_token: str | None = None) -> dict[str, Any]:
        tool = self._tools[name]
        started = time.monotonic()
        try:
            if tool.allowed_agents and agent not in tool.allowed_agents:
                raise PermissionError("agent is not allowed to call this tool")
            if tool.side_effect == SideEffect.EXTERNAL_ACTION:
                raise PermissionError("agents cannot execute purchases, payments, or external actions")
            if name in {"calibration.promote", "data.overwrite_observation", "observation.update_measured"}:
                raise PermissionError("this action is prohibited; use the audited human or promotion-gate workflow")
            if tool.requires_approval and tool.side_effect >= SideEffect.WRITE_STATE:
                if (
                    not approval_token
                    or self.approval_validator is None
                    or not self.approval_validator(approval_token, name, args)
                ):
                    raise ApprovalRequiredError("valid scoped approval token required")
            unknown = set(args) - set(tool.input_model.model_fields)
            if unknown:
                raise ValueError(f"unknown input fields: {sorted(unknown)}")
            payload = tool.input_model.model_validate(args)
            if tool.timeout_s <= 0:
                raise TimeoutError("tool execution budget exhausted")
            result = tool.output_model.model_validate(tool.handler(payload))
            body = result.model_dump(mode="json")
            encoded = json.dumps(body, sort_keys=True, default=str).encode()
            artifact_ref = None
            if len(encoded) > self.max_inline_bytes:
                if self.artifact_store is None:
                    raise RuntimeError("large tool output requires an artifact store; payload was not truncated silently")
                artifact_ref = self.artifact_store(body)
                body = {"truncated": True, "serialized_bytes": len(encoded), "artifact_ref": artifact_ref}
            return {
                "ok": True,
                "result": body,
                "result_hash": sha256(encoded).hexdigest(),
                "artifact_ref": artifact_ref,
                "duration_s": time.monotonic() - started,
            }
        except FarmTwinError as exc:
            return {"ok": False, "error": exc.to_dict()}
        except Exception as exc:
            return {"ok": False, "error": {"code": type(exc).__name__.lower(), "message": str(exc), "context": {}}}
        finally:
            self.calls.append({"name": name, "agent": agent, "duration_s": time.monotonic() - started})
