"""
FILE: farm_twin/optimization/milp_cvar.py
PURPOSE: Solve the risk-aware allocation with Pyomo + an open-source MILP solver (HiGHS via `appsi_highs`; fallbacks CBC/GLPK). The formulation below was PROTOTYPED AND SOLVED to optimality during blueprint creation (3 plots x 3 options x 50 scenarios; result: optimal).

FORMULATION (maximise (1-lambda)*E[NPV] + lambda*CVaR_alpha):
   sets P (plots), O (options), S (scenarios, equiprobable weights 1/|S| or supplied probabilities pi_s)
   vars x[p,o] binary ; eta free (VaR proxy) ; z[s] >= 0 (shortfall)
   NPV_s = sum_{p,o} payoff[p,o,s]*x[p,o]
   z[s] >= eta - NPV_s            for all s
   CVaR = eta - 1/(1-alpha) * sum_s pi_s*z[s]                  (Rockafellar-Uryasev; alpha e.g. 0.8 => mean of worst 20 %)
   sum_o x[p,o] = 1  for all p ; sum_{p,o} capex[p,o]*x[p,o] <= budget ; + water/labour constraints
   objective = (1-lambda)*sum_s pi_s*NPV_s + lambda*CVaR
 Minimal Pyomo skeleton to reproduce (Codex: implement properly with named constraint rules):
     m.x = Var(P,O,within=Binary); m.eta = Var(); m.z = Var(S, within=NonNegativeReals)
     m.cv = Constraint(S, rule=lambda m,s: m.z[s] >= m.eta - npv(m,s))
     cvar = m.eta - (1/((1-alpha)*len(S)))*sum(m.z[s] for s in S)
     SolverFactory('appsi_highs').solve(m)
 PARETO / EPSILON-CONSTRAINT: sweep lambda in [0,1] (11 points) AND epsilon-constraints on secondary objectives (water, carbon) -> list of non-dominated allocations; remove dominated points; return frontier + for each point the full allocation, E[NPV], CVaR, water, carbon, capex.
 ROBUST VARIANT: worst-case over a scenario subset (minimise max regret): regret_s = best_possible_NPV_s - NPV_s (best by per-scenario solve), minimise t >= regret_s.
 CHANCE-CONSTRAINT: P(NPV<0) <= eps via binary b_s with NPV_s >= -M*b_s, sum pi_s b_s <= eps.
 SENSITIVITY OF DECISION: solve with perturbed payoffs (bootstrap scenarios) and report the frequency each allocation is optimal ('decision stability'); present stability to the user - if the best allocation is chosen in <50 % of bootstraps, say the decision is not robust.
 SOLVER HANDLING: time_limit, mip_gap from config; if infeasible, run IIS-like relaxation: add slack to each constraint with penalty and report which constraints bind; never return silently empty.
 CP-SAT (OR-Tools) is an allowed second solver ONLY for pure scheduling subproblems (planting dates/labour) - not for the CVaR model.
TESTS: reproduce the 3x3x50 prototype structure (optimal status, one option per plot, CVaR <= mean); lambda=0 equals expected-value maximiser; lambda=1 maximises CVaR; infeasible budget -> relaxation report.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
import numpy as np


@dataclass(frozen=True)
class AllocationResult:
    option_indices: tuple[int, ...] | None
    expected_npv: float | None
    cvar: float | None
    objective: float | None
    status: str
    relaxation_report: tuple[str, ...] = ()


def lower_cvar(values: np.ndarray, alpha: float, probabilities: np.ndarray | None = None) -> float:
    x = np.asarray(values, float).ravel()
    if not 0 < alpha < 1 or not len(x):
        raise ValueError("alpha must be in (0,1) and values non-empty")
    p = np.full(len(x), 1 / len(x)) if probabilities is None else np.asarray(probabilities, float)
    if p.shape != x.shape or not np.isclose(p.sum(), 1) or np.any(p < 0):
        raise ValueError("invalid scenario probabilities")
    # Exact lower-tail integral, including partial probability mass at the quantile.
    order = np.argsort(x)
    mass = 1 - alpha
    used = 0.0
    total = 0.0
    for idx in order:
        take = min(float(p[idx]), mass - used)
        total += take * x[idx]
        used += take
        if used >= mass - 1e-12:
            break
    return total / mass


def solve_enumerated(
    payoff: np.ndarray,
    capex: np.ndarray,
    budget: float,
    alpha: float = 0.8,
    risk_lambda: float = 0.0,
    probabilities: np.ndarray | None = None,
    max_combinations: int = 100000,
) -> AllocationResult:
    """Exact small-instance fallback; production-scale Pyomo/HiGHS solver remains to be wired."""
    a = np.asarray(payoff, float)
    c = np.asarray(capex, float)
    if a.ndim != 3 or c.shape != a.shape[:2] or not 0 <= risk_lambda <= 1:
        raise ValueError("payoff shape [plot,option,scenario] required")
    counts = [int(np.isfinite(c[p]).sum()) for p in range(c.shape[0])]
    total = int(np.prod(counts))
    if total > max_combinations:
        raise ValueError("enumeration cap exceeded; install/enable Pyomo HiGHS backend")
    pi = np.full(a.shape[2], 1 / a.shape[2]) if probabilities is None else np.asarray(probabilities, float)
    best = None
    feasible = 0
    for combo in product(*(range(n) for n in counts)):
        cost = sum(c[p, o] for p, o in enumerate(combo))
        if cost > budget:
            continue
        vals = np.sum([a[p, o] for p, o in enumerate(combo)], axis=0)
        if not np.isfinite(vals).all():
            continue
        mean = float(np.dot(pi, vals))
        cv = lower_cvar(vals, alpha, pi)
        objective = (1 - risk_lambda) * mean + risk_lambda * cv
        feasible += 1
        if best is None or objective > best.objective:
            best = AllocationResult(tuple(combo), mean, cv, objective, "optimal")
    if best is not None:
        return best
    return AllocationResult(
        None, None, None, None, "infeasible", ("capex budget or payoff constraints prevent any allocation",)
    )


def solve_pyomo(
    payoff: np.ndarray,
    capex: np.ndarray,
    budget: float,
    alpha: float = 0.8,
    risk_lambda: float = 0.5,
    probabilities: np.ndarray | None = None,
    solver_name: str = "appsi_highs",
    time_limit_s: float = 120.0,
    mip_gap: float = 0.001,
) -> AllocationResult:
    """Solve the scenario CVaR MILP. Optional Pyomo/HiGHS is imported only at call time."""
    a = np.asarray(payoff, dtype=float)
    cost = np.asarray(capex, dtype=float)
    if a.ndim != 3 or cost.shape != a.shape[:2]:
        raise ValueError("payoff must have shape [plot,option,scenario] and capex [plot,option]")
    if not 0 < alpha < 1 or not 0 <= risk_lambda <= 1 or budget < 0:
        raise ValueError("invalid alpha, risk_lambda, or budget")
    p_count, o_count, s_count = a.shape
    pi = np.full(s_count, 1.0 / s_count) if probabilities is None else np.asarray(probabilities, dtype=float)
    if pi.shape != (s_count,) or np.any(pi < 0) or not np.isclose(pi.sum(), 1):
        raise ValueError("scenario probabilities must be non-negative and sum to one")
    valid_options = {(p, o) for p in range(p_count) for o in range(o_count) if np.isfinite(cost[p, o]) and np.isfinite(a[p, o]).all()}
    if any(not any(p == plot for p, _ in valid_options) for plot in range(p_count)):
        return AllocationResult(None, None, None, None, "infeasible", ("a plot has no complete payoff option",))
    try:
        import pyomo.environ as pyo
        from pyomo.opt import SolverStatus, TerminationCondition
    except ImportError as exc:
        raise RuntimeError("install the planning extra to solve the Pyomo MILP") from exc
    model = pyo.ConcreteModel(name="farm_twin_cvar_allocation")
    model.P = pyo.RangeSet(0, p_count - 1)
    model.O = pyo.RangeSet(0, o_count - 1)
    model.S = pyo.RangeSet(0, s_count - 1)
    model.x = pyo.Var(model.P, model.O, domain=pyo.Binary)
    for p in range(p_count):
        for o in range(o_count):
            if (p, o) not in valid_options:
                model.x[p, o].fix(0)
    model.eta = pyo.Var(domain=pyo.Reals)
    model.z = pyo.Var(model.S, domain=pyo.NonNegativeReals)

    def choose_one_rule(m, p):
        return sum(m.x[p, o] for o in m.O) == 1

    def budget_rule(m):
        return sum(cost[p, o] * m.x[p, o] for p in range(p_count) for o in range(o_count) if (p, o) in valid_options) <= budget

    def scenario_npv(m, s):
        return sum(a[p, o, s] * m.x[p, o] for p, o in valid_options)

    def shortfall_rule(m, s):
        return m.z[s] >= m.eta - scenario_npv(m, s)

    cvar = model.eta - sum(float(pi[s]) * model.z[s] for s in range(s_count)) / (1 - alpha)
    expected = sum(float(pi[s]) * scenario_npv(model, s) for s in range(s_count))
    model.one_option = pyo.Constraint(model.P, rule=choose_one_rule)
    model.capex_budget = pyo.Constraint(rule=budget_rule)
    model.cvar_shortfall = pyo.Constraint(model.S, rule=shortfall_rule)
    model.objective = pyo.Objective(expr=(1 - risk_lambda) * expected + risk_lambda * cvar, sense=pyo.maximize)
    solver = pyo.SolverFactory(solver_name)
    if solver is None or not solver.available(exception_flag=False):
        return solve_enumerated(a, cost, budget, alpha, risk_lambda, pi)
    if solver_name == "appsi_highs":
        solver.options["time_limit"] = time_limit_s
        solver.options["mip_rel_gap"] = mip_gap
    result = solver.solve(model, tee=False)
    if result.solver.status != SolverStatus.ok or result.solver.termination_condition not in {
        TerminationCondition.optimal,
        TerminationCondition.feasible,
        TerminationCondition.maxTimeLimit,
    }:
        if result.solver.termination_condition == TerminationCondition.infeasible:
            return AllocationResult(None, None, None, None, "infeasible", ("capex budget and assignment constraints conflict",))
        raise RuntimeError(f"MILP solver ended with {result.solver.status}/{result.solver.termination_condition}")
    allocation = tuple(max(range(o_count), key=lambda o: pyo.value(model.x[p, o])) for p in range(p_count))
    values = np.sum([a[p, o] for p, o in enumerate(allocation)], axis=0)
    mean = float(np.dot(pi, values))
    cv = lower_cvar(values, alpha, pi)
    objective_value = float(pyo.value(model.objective))
    return AllocationResult(allocation, mean, cv, objective_value, str(result.solver.termination_condition))


def solve_chance_constrained(
    payoff: np.ndarray,
    capex: np.ndarray,
    budget: float,
    max_loss_probability: float,
    probabilities: np.ndarray | None = None,
    solver_name: str = "appsi_highs",
) -> AllocationResult:
    """Maximize expected NPV subject to a scenario-weighted probability-of-loss limit."""
    import pyomo.environ as pyo

    values = np.asarray(payoff, float)
    costs = np.asarray(capex, float)
    if values.ndim != 3 or costs.shape != values.shape[:2] or not 0 <= max_loss_probability <= 1:
        raise ValueError("invalid payoff, capex, or chance constraint")
    plots, options, scenarios = values.shape
    pi = np.full(scenarios, 1 / scenarios) if probabilities is None else np.asarray(probabilities, float)
    if pi.shape != (scenarios,) or np.any(pi < 0) or not np.isclose(pi.sum(), 1):
        raise ValueError("scenario probabilities must sum to one")
    valid = [(p, o) for p in range(plots) for o in range(options) if np.isfinite(costs[p, o]) and np.isfinite(values[p, o]).all()]
    if any(not any(p == plot for p, _ in valid) for plot in range(plots)):
        return AllocationResult(None, None, None, None, "infeasible", ("a plot has no complete payoff option",))
    model = pyo.ConcreteModel()
    model.P = pyo.RangeSet(0, plots - 1)
    model.O = pyo.RangeSet(0, options - 1)
    model.S = pyo.RangeSet(0, scenarios - 1)
    model.x = pyo.Var(model.P, model.O, domain=pyo.Binary)
    model.loss = pyo.Var(model.S, domain=pyo.Binary)
    model.npv = pyo.Expression(model.S, rule=lambda m, s: sum(values[p, o, s] * m.x[p, o] for p, o in valid))
    for p in range(plots):
        for o in range(options):
            if (p, o) not in valid:
                model.x[p, o].fix(0)
    big_m = max(1.0, float(sum(np.max(np.abs(values[p, o])) for p, o in valid)))
    model.assignment = pyo.Constraint(model.P, rule=lambda m, p: sum(m.x[p, o] for o in m.O) == 1)
    model.budget = pyo.Constraint(expr=sum(costs[p, o] * model.x[p, o] for p, o in valid) <= budget)
    model.loss_indicator = pyo.Constraint(model.S, rule=lambda m, s: m.npv[s] + big_m * m.loss[s] >= 0)
    model.loss_limit = pyo.Constraint(expr=sum(float(pi[s]) * model.loss[s] for s in range(scenarios)) <= max_loss_probability)
    model.objective = pyo.Objective(expr=sum(float(pi[s]) * model.npv[s] for s in range(scenarios)), sense=pyo.maximize)
    solver = pyo.SolverFactory(solver_name)
    if not solver.available(exception_flag=False):
        raise RuntimeError(f"MILP solver {solver_name} unavailable")
    result = solver.solve(model)
    if result.solver.termination_condition != pyo.TerminationCondition.optimal:
        return AllocationResult(None, None, None, None, str(result.solver.termination_condition), ("chance-constrained MILP infeasible or not optimal",))
    allocation = tuple(max(range(options), key=lambda o: pyo.value(model.x[p, o])) for p in range(plots))
    scenario_values = np.sum([values[p, o] for p, o in enumerate(allocation)], axis=0)
    mean = float(np.dot(pi, scenario_values))
    cvar = lower_cvar(scenario_values, 0.8, pi)
    return AllocationResult(allocation, mean, cvar, mean, str(result.solver.termination_condition))


def minimax_regret_enumerated(payoff: np.ndarray, capex: np.ndarray, budget: float) -> AllocationResult:
    """Small-case robust optimization over complete allocation combinations."""
    a = np.asarray(payoff, float)
    c = np.asarray(capex, float)
    if a.ndim != 3 or c.shape != a.shape[:2] or not np.isfinite(budget):
        raise ValueError("payoff must be [plot, option, scenario] with matching capex")
    valid = [[o for o in range(a.shape[1]) if np.isfinite(c[p, o]) and np.isfinite(a[p, o]).all()]
             for p in range(a.shape[0])]
    if any(not options for options in valid):
        return AllocationResult(None, None, None, None, "infeasible", ("a plot has no complete payoff option",))
    combinations = list(product(*valid))
    scenario_best = np.asarray([
        max(sum(a[p, o, s] for p, o in enumerate(combo)) for combo in combinations)
        for s in range(a.shape[2])
    ])
    best = None
    for combo in combinations:
        if sum(c[p, o] for p, o in enumerate(combo)) > budget:
            continue
        vals = np.sum([a[p, o] for p, o in enumerate(combo)], axis=0)
        regret = scenario_best - vals
        worst = float(np.max(regret))
        candidate = AllocationResult(tuple(combo), float(np.mean(vals)), lower_cvar(vals, 0.8), -worst, "optimal")
        if best is None or candidate.objective > best.objective:
            best = candidate
    return best or AllocationResult(None, None, None, None, "infeasible", ("budget prevents a feasible allocation",))


def decision_stability(payoff: np.ndarray, capex: np.ndarray, budget: float, replicates: int, rng: np.random.Generator,
                       alpha: float = 0.8, risk_lambda: float = 0.5) -> dict[tuple[int, ...], float]:
    """Bootstrap common scenario columns and report allocation selection frequency."""
    a = np.asarray(payoff, float)
    if a.ndim != 3 or replicates < 1:
        raise ValueError("payoff must be 3D and replicates positive")
    counts: dict[tuple[int, ...], int] = {}
    for _ in range(replicates):
        sample = rng.integers(0, a.shape[2], size=a.shape[2])
        result = solve_enumerated(a[:, :, sample], capex, budget, alpha, risk_lambda)
        if result.option_indices is not None:
            counts[result.option_indices] = counts.get(result.option_indices, 0) + 1
    return {allocation: count / replicates for allocation, count in counts.items()}
