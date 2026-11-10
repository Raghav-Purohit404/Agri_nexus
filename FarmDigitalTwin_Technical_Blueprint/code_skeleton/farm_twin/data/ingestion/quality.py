"""
FILE: farm_twin/data/ingestion/quality.py
PURPOSE: Data quality engine used by the Data Quality Agent AND by batch imports.

IMPLEMENT checks (each returns Issue(severity, code, variable, plot, message, suggested_action)):
  range_check (core.units.RANGES); unit_check; missing_check (required-variable matrix per model: e.g. AquaCrop-native needs sand/clay/OM or theta_wp/fc/sat/ksat per layer);
  duplicate_check (same key within tolerance); inconsistency_check:
      - physical: theta_fc <= theta_sat, theta_wp < theta_fc, Tmax >= Tmin, rain >= 0, Rs <= Ra (extra-terrestrial; 1.0 tolerance 5%), ea <= es
      - cross-variable: sand+silt+clay=100; ESP vs SAR (ESP ~ 100*(-0.0126+0.01475*SAR)/(1+(-0.0126+0.01475*SAR)) within +/- 5 points else warn)
  stale_check(rules per variable: weather forecast > 24 h; prices > 7 d; soil biology/OC > 3 y; satellite > 15 d)
  outlier_check on series: robust z (median/MAD) > 5 flagged, not removed;
  gap_report(series): list of gaps with lengths; gap_fill(series, method) ONLY for weather and ONLY short gaps (<= 3 d linear for temperature, 0 for rain unless another source covers it) producing ESTIMATED values with flag `gap_filled`.
  completeness_score(plot, model) in [0,1] per required-variable matrix -> drives Value-of-Information ranking (see voi/).
TESTS: each check has positive/negative fixtures; gap-fill never touches MEASURED rain.
"""
