"""
FILE: farm_twin/calibration/metrics.py
PURPOSE: Scoring functions. IMPLEMENT (numpy): rmse, mae, bias, nse = 1 - sum((o-p)^2)/sum((o-mean(o))^2), kge = 1 - sqrt((r-1)^2 + (alpha-1)^2 + (beta-1)^2) (alpha = sd_p/sd_o, beta = mean_p/mean_o), d_index (Willmott), crps_ensemble(samples, obs) = mean|X-y| - 0.5*mean|X-X'| (fair/unbiased variant for finite ensembles), interval_coverage(lo, hi, obs), pit_values, reliability_diagram bins, pinball loss for quantiles, relative errors for yield (%), r2. All handle NaN by pairwise deletion and return n used.
TESTS: hand-computed small arrays; CRPS of a point mass equals MAE.
"""
