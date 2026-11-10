"""
FILE: farm_twin/optimization/problem.py
PURPOSE: Decision problem definition: which land-use/management bundle per plot (and farm-level assets) maximises risk-adjusted value subject to physical, water, budget and user constraints.

DECISION STRUCTURE (two-stage):
  Stage 1 (here-and-now, deterministic): option x_{p,o} in {0,1}: plot p adopts option o. Options per plot come from eligible_uses: CROP_BUNDLE(crop sequence, irrigation policy, fertility plan) | PV_GROUND(config) | AGRIVOLTAIC(config, crop) | FALLOW_RECLAIM(amendment plan) | WATER_STORAGE | MIXED strips (split plot into sub-areas: allow `split_resolution` = e.g. 25 % chunks, each a separate decision unit to keep the model linear).
  Stage 2 (recourse, scenario-dependent): irrigation purchase/shortfall, in-season adjustments (modelled via the irrigation policy inside the simulator, not as free LP variables).
PAYOFF TABLE PRECOMPUTATION (the expensive part, done by the simulator): for every (p,o) and every scenario s: NPV_{p,o,s}, water_use_{p,o,s,month}, capex_{p,o,year}, soil_carbon_delta_{p,o,s}, ece_end_{p,o,s}, labour_{p,o,month}. The optimisation layer is therefore LINEAR (MILP) in x - non-linear agronomy stays in the simulator. Interaction effects (e.g. shared pump, shared water source) handled by farm-level constraints below, and cross-plot effects (shade on neighbours) pre-evaluated as joint options for adjacent plots when needed (option 'PV on A with neighbour B shaded' is a pair option).
CONSTRAINTS (farm level): sum_o x_{p,o} = 1 each plot; capex budget by year: sum capex*x <= budget_t ; water: sum_{p,o} water_{p,o,s,m} x_{p,o} <= supply_{s,m} + purchase_{s,m}, purchase >= 0 with cost; labour; electricity self-consumption cap if tariffs require; policy constraints (e.g. at least X % cropped, no PV on plot A); risk: CVaR constraint or objective; agronomic: rotation rules enforced by option definition (legume after cereal etc.); minimum soil carbon change >= 0 (optional constraint).
OBJECTIVES (selectable / multi-objective): f1 = E[NPV] ; f2 = CVaR_alpha(NPV) ; f3 = -water_use ; f4 = soil carbon gain ; f5 = -capex ; f6 = P(min cash < 0) (via chance constraint with big-M binaries, optional).
OUTPUT: DecisionProblem dataclass holding index sets, payoff arrays (numpy), constraint config; build_from_simulations(sim_results, config).
"""
