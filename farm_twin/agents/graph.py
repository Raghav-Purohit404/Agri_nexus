"""
FILE: farm_twin/agents/graph.py
PURPOSE: The LangGraph StateGraph wiring all agents. Supervisor-worker pattern with deterministic edges where possible; LLM routing only where judgement is needed.

IMPLEMENT with langgraph (StateGraph, START/END, Command for routing+state updates, Send for parallel fan-out, interrupt() for human approval, RetryPolicy on nodes with transient failures, PostgresSaver checkpointer):
  nodes: intake -> supervisor -> {data_ingestion, data_quality, geospatial, soil_scientist, agronomist, water_engineer, solar_engineer, agrivoltaic_analyst, finance_analyst, risk_analyst, planner_optimizer, calibration_validator, explainer, governance} -> supervisor ... -> explainer -> END
  SUPERVISOR: (1) classify request -> task plan from templates (deterministic, templates in agents/plans.yaml): e.g. PLAN_LANDUSE = [ensure_data_complete, quality_gate, soil_assessment, water_assessment, candidate_generation (crop/PV/agrivoltaic/reclaim options per plot), simulate_ensembles (parallel Send per plot-option), finance, risk, optimise, validation_check, explain, approval]; (2) dispatch tasks in dependency order, parallel where independent; (3) after each worker, evaluate: failed? missing data? -> may add a `ClarificationRequest` and PAUSE via interrupt() to ask the user; (4) enforce budget (max tool calls, wall-clock); (5) never answers science questions itself.
  QUALITY GATE (conditional edge): if completeness_score < threshold for a required model -> do NOT proceed to optimisation; instead produce `what_is_missing` and VOI-ranked data requests; allow user to proceed with ESTIMATED inputs explicitly ('proceed with assumptions') -> run continues and every output carries the assumptions banner.
  VALIDATION GATE before any recommendation is shown: checks calibration status of models used (validated vs placeholder/unvalidated) and attaches warnings; blocks `recommendation` for crops with placeholder parameters unless user acknowledged.
  GOVERNANCE NODE: any proposed change to ACTUAL records/plans routes through interrupt() -> human approves/rejects/modifies; resume with Command(resume=decision); only then tools with approval requirement execute.
  OBSERVABILITY: every node run logged (agent_run, tool_call); trace ids; LangSmith-compatible tracing optional; cost & latency counters.
  DETERMINISM: temperature 0, tool outputs are the only source of numbers; a post-processing `groundedness_check` node verifies every number in the final answer maps to an EvidenceItem (regex + tolerance 1 %); failures trigger one regeneration then a plain refusal to state the number.
TESTS: graph compiles; happy-path PLAN_LANDUSE on a fixture farm with a FAKE LLM (scripted tool calls) ; interrupt/resume round trip; failed tool -> supervisor adds clarification; budget exhaustion ends gracefully with partial results.
"""

from __future__ import annotations

from typing import Any, Callable


def build_graph(workers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] | None = None, checkpointer: Any = None):
    """Build dependency-injected LangGraph workflow; production PostgreSQL saver is supplied by deployment."""
    try:
        from langgraph.graph import StateGraph, START, END
        from langgraph.types import interrupt
    except ImportError as exc:
        raise RuntimeError("LangGraph is required to compile the agent workflow") from exc
    from farm_twin.agents.state import AgentState

    graph = StateGraph(AgentState)

    def intake(state):
        return {"messages": state.get("messages", []), "evidence": state.get("evidence", [])}

    def supervisor(state):
        if state.get("pending_approval"):
            return {"active_worker": "__governance__"}
        tasks = list(state.get("plan", []))
        left = int(state.get("budget", {}).get("tool_calls_left", 0))
        pending = next((i for i, task in enumerate(tasks) if task.get("status", "PENDING") == "PENDING"), None)
        if pending is None:
            return {"active_worker": None}
        task = dict(tasks[pending])
        worker_name = task.get("worker") or task.get("name")
        if left <= 0:
            task["status"] = "BLOCKED_ON_USER"
            task["reason"] = "tool-call budget exhausted"
            tasks[pending] = task
            question = {"question": "The analysis stopped at its tool-call budget. Increase the budget or narrow the request."}
            return {"active_worker": None, "plan": tasks, "open_questions": [*state.get("open_questions", []), question]}
        if worker_name not in names:
            task["status"] = "FAILED"
            task["reason"] = f"worker not configured: {worker_name}"
            tasks[pending] = task
            return {"active_worker": None, "plan": tasks}
        task["status"] = "RUNNING"
        tasks[pending] = task
        budget = {**state.get("budget", {}), "tool_calls_left": left - 1}
        return {"active_worker": worker_name, "plan": tasks, "budget": budget}

    def worker(name):
        def call(state):
            if name not in (workers or {}):
                return {
                    "open_questions": [
                        *state.get("open_questions", []),
                        {"question": f"Worker {name} is not configured"},
                    ]
                }
            output = (workers or {})[name](state)
            output = output or {}
            tasks = list(state.get("plan", []))
            for index, task in enumerate(tasks):
                if task.get("status") == "RUNNING" and (task.get("worker") or task.get("name")) == name:
                    tasks[index] = {**task, "status": "DONE"}
                    break
            return {
                **output,
                "plan": output.get("plan", tasks),
                "evidence": [*state.get("evidence", []), *output.get("evidence", [])],
                "artifacts": {**state.get("artifacts", {}), **output.get("artifacts", {})},
                "active_worker": None,
            }

        return call

    def explainer(state):
        return {"evidence": state.get("evidence", []), "artifacts": state.get("artifacts", {})}

    def governance(state):
        decision = interrupt(state["pending_approval"])
        return {"pending_approval": None, "approval_decision": decision}

    def route_supervisor(state):
        active = state.get("active_worker")
        if active == "__governance__":
            return "governance"
        return active if active in names else "explainer"

    graph.add_node("intake", intake)
    graph.add_node("supervisor", supervisor)
    graph.add_node("explainer", explainer)
    graph.add_node("governance", governance)
    names = tuple((workers or {}).keys())
    for name in names:
        graph.add_node(name, worker(name))
    graph.add_edge(START, "intake")
    graph.add_edge("intake", "supervisor")
    if names:
        graph.add_conditional_edges(
            "supervisor",
            route_supervisor,
            {**{name: name for name in names}, "governance": "governance", "explainer": "explainer"},
        )
        for name in names:
            graph.add_edge(name, "supervisor")
        graph.add_edge("governance", "supervisor")
    else:
        graph.add_conditional_edges("supervisor", route_supervisor, {"governance": "governance", "explainer": "explainer"})
        graph.add_edge("governance", "supervisor")
    graph.add_edge("explainer", END)
    return graph.compile(checkpointer=checkpointer)
