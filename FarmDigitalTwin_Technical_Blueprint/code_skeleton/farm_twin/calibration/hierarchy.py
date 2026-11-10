"""
FILE: farm_twin/calibration/hierarchy.py
PURPOSE: Four-level parameter hierarchy with partial pooling. Prevents overfitting a single plot with sparse data while allowing plot-specific learning when evidence exists.

LEVELS: GENERIC (published/default) -> REGIONAL (arid NW India, district) -> FARM -> PLOT.
MODEL (for each calibratable parameter theta_j, on a suitable transform: log for positive rates, logit for fractions):
   theta_generic_j ~ fixed prior N(mu_g, sd_g^2)        (from the crop library / literature; sd encodes confidence)
   theta_region_j  ~ N(theta_generic_j, tau_r^2)
   theta_farm_j    ~ N(theta_region_j, tau_f^2)
   theta_plot_{j,k} ~ N(theta_farm_j, tau_p^2)          k = plot
   observations y_{k,m} ~ N(f_m(theta_plot_k, x), sigma_m^2)  m = variable (yield, canopy cover, soil moisture, EC ...)
 tau_* have half-normal hyperpriors with scales set so that, with no data, plots shrink ~90 % to the farm value. With n_k observations the posterior mean is the precision-weighted compromise: w = (n_k/sigma^2)/(n_k/sigma^2 + 1/tau_p^2).
 resolve_effective(model, plot_id) returns the posterior at the most specific level that has PASSED the promotion gate; a candidate that failed is never used.
 CALIBRATABLE SETS (small!): crop: {CGC, CCx, WP (or RUE), HI0, Zmax, Kcb, p_up/p_lo of stomata}; soil: {Ksat/tau, REW, theta_fc offset}; carbon: {k multipliers}; salinity: {a,b threshold-slope}; nutrients: {k_nit, f_uptake, mineralisation multiplier}; PV: {soiling rate, gamma, system loss}; agrivoltaic: {tau_eff, f_par, wind factor, dT}. Parameters not in the list stay fixed - never calibrate more parameters than data supports (rule: n_obs >= 5 * n_params for plot level; else do not fit plot level).
 IDENTIFIABILITY: before fitting compute local sensitivity (Morris/Sobol on the prior) and profile-likelihood / posterior-contraction checks; parameters with contraction < 20 % are reported as 'not identified by these data' and left at the parent level.
TESTS: shrinkage formula; plot with 0 observations equals farm; farm with no data equals region; non-identified parameter stays at parent.
"""
