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
