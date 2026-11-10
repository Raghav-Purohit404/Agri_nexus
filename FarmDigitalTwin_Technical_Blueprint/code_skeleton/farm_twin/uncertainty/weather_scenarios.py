"""
FILE: farm_twin/uncertainty/weather_scenarios.py
PURPOSE: Generate joint weather scenario ensembles for 1-season and 10-year horizons. Weather is the dominant risk in arid rainfed/irrigated systems.

IMPLEMENT (selectable):
  1. HISTORICAL_REPLAY: each historical year (e.g. 1990-2025) is one scenario (preserves inter-variable correlation; N ~ 35). Default for season-level decisions.
  2. BLOCK_BOOTSTRAP for multi-year horizons: sample years with replacement (or monthly blocks of 15-30 days, preserving intra-season persistence), concatenate; N=200-1000.
  3. PARAMETRIC GENERATOR (when long records absent): first-order two-state Markov chain for rain occurrence (p01, p11 per month), gamma (or mixed-exponential) distribution for wet-day amounts (shape, scale per month), temperatures from a multivariate normal conditioned on wet/dry state with monthly means/covariances and lag-1 autocorrelation (WGEN-type: residual AR(1) of standardised Tmax, Tmin, Rs). Fit by method of moments/MLE per month; verify generated statistics (mean annual rain, wet-day freq, dry-spell length distribution, Tmax/Tmin means) against the observed within tolerances (mean annual rain +/-10 %, dry-spell P90 +/-15 %).
  4. CLIMATE_SHIFT: apply delta factors (monsoon rain scale, +dT, heat-wave frequency multiplier) to any of the above; scenarios labelled explicitly; never presented as forecasts.
  5. SEASONAL FORECAST conditioning (optional): if an IMD/ECMWF tercile forecast is supplied, reweight historical years by analog similarity (e.g. ENSO/IOD state) with weights bounded [0.5,2] - flagged experimental.
  OUTPUT: WeatherScenarioSet(scenarios: array[N, T, vars], year_labels, method, fit_diagnostics, seed). Shared across plots (spatially identical at farm scale) and shared across candidate plans (common random numbers).
TESTS: Markov chain reproduces wet-day frequency; generator diagnostics; replay count; CRN identical across plans.
"""
