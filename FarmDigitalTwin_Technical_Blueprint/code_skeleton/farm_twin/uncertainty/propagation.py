"""
FILE: farm_twin/uncertainty/propagation.py
PURPOSE: Monte Carlo over THREE uncertainty sources, kept separate so reports can attribute variance: (A) weather (aleatory), (B) parameter/structural (epistemic; posterior draws), (C) economic (prices, tariffs, costs).
IMPLEMENT: sample_params(parameter_set, n, rng) (posterior draws or prior if not calibrated), sample_prices(price_model, n, rng, corr_with_yield), joint_runs(scenario, n_weather, n_param, n_price, rng) with a budget cap: total sims = n_weather x n_param (default 50 x 20 = 1000) but economics post-processing is cheap so n_price may be larger. Variance decomposition by nested ANOVA (law of total variance): Var(Y) = E[Var(Y|weather)] + Var(E[Y|weather]) etc. Latin hypercube sampling for parameters (scipy.stats.qmc), Sobol sequence for economics.
 Output summaries: mean, sd, quantiles (5,25,50,75,95), P(Y<threshold), CVaR; ALWAYS return samples for downstream optimisation.
 Convergence diagnostic: bootstrap SE of mean and of 5th percentile; auto-increase N until relative SE < 2 % (cap).
TESTS: variance decomposition sums to total on synthetic additive model; LHS marginals uniform.
"""
