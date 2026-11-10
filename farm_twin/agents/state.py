"""
FILE: farm_twin/agents/state.py
PURPOSE: Shared typed state for the multi-agent LangGraph graph.

IMPLEMENT (TypedDict/pydantic with reducers):
  class AgentState:
     messages: Annotated[list, add_messages]        # conversation
     request: UserRequest                           # parsed intent: {kind in [ONBOARD, ANALYSE_PLOT, PLAN_LANDUSE, WHAT_IF, EXPLAIN, UPDATE_DATA, REVIEW_OUTCOMES], plot_ids, horizon, constraints, language}
     plan: list[Task]                               # supervisor's task list with status {PENDING, RUNNING, DONE, FAILED, BLOCKED_ON_USER}
     evidence: Annotated[list[EvidenceItem], append]   # every claim-bearing result: {id, tool_call_id, summary, numbers[Quantified], provenance, model_versions, input_hash}
     artifacts: dict[str, ArtifactRef]              # scenario ids, sim_run ids, recommendation ids, report ids
     open_questions: list[ClarificationRequest]     # blocking questions for the user (units, missing data)
     pending_approval: ApprovalRequest | None
     budget: {tool_calls_left, wallclock_s_left, tokens_left}
     flags: {unvalidated_models: [..], placeholder_params: [..], stale_data: [..]}
  Reducers: evidence is append-only; artifacts merge; tasks update by id.
  Checkpointing: PostgreSQL checkpointer (langgraph-checkpoint-postgres) keyed by thread_id = user session; resumable after approval interrupts and process restarts.
RULE: an agent may only state numbers that exist in `evidence` (see evals/groundedness).
"""

from __future__ import annotations

from typing import Any, TypedDict, NotRequired


class AgentState(TypedDict):
    messages: list[dict[str, Any]]
    request: dict[str, Any]
    plan: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    artifacts: dict[str, Any]
    open_questions: list[dict[str, Any]]
    pending_approval: NotRequired[dict[str, Any] | None]
    budget: dict[str, float | int]
    flags: dict[str, list[str]]


def append_evidence(state: AgentState, items: list[dict[str, Any]]) -> AgentState:
    return {**state, "evidence": [*state.get("evidence", []), *items]}


def merge_artifacts(state: AgentState, artifacts: dict[str, Any]) -> AgentState:
    return {**state, "artifacts": {**state.get("artifacts", {}), **artifacts}}
