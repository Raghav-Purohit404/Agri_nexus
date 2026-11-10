"""
FILE: farm_twin/calibration/bayes.py
PURPOSE: Posterior estimation for the hierarchy using methods suited to expensive simulators with few observations.

METHODS (selectable, default first):
  1. Ensemble MCMC (affine-invariant, `emcee` allowed as dependency) over the <= 8 parameters of one level at a time (conditional on parent posterior means; 'sequential' hierarchical updating), 32+ walkers, 2,000+ steps, convergence by R-hat < 1.05 and ESS > 400; simulator calls are cheap enough (<10 ms/season vectorised) to run 100k evaluations.
  2. Approximate Bayesian Computation SMC (when likelihood is awkward, e.g. only season yield observed): distance = normalised RMSE across observed variables; tolerance schedule by quantiles.
  3. GLUE (informal likelihood) ONLY as a diagnostic, never for promotion.
  LIKELIHOOD: Gaussian on transformed outputs with observation error sigma_m = sqrt(sigma_meas^2 + sigma_struct^2); sigma_struct estimated (inverse-gamma prior) - captures model discrepancy; yield: relative error; soil moisture: sensor error (typ. 0.02-0.03 m3/m3) ; satellite fcover: mixed-pixel inflated error; EC: log-normal.
  OUTPUT: PosteriorSample (draws, summary, diagnostics), written to parameter_set(posterior). Draws are what the engine propagates (param_draws).
  GUARDS: reject fits if prior-posterior overlap suggests prior-data conflict (prior predictive check p<0.01) and flag for expert review rather than silently widening.
TESTS: recover known parameters from synthetic data (twin experiment) within 95 % intervals in >= 90 % of 100 trials (calibration coverage test); R-hat computation.
"""
