# Notes per model family
Crop: L1 engine is an original implementation of published AquaCrop-style equations; validated only if golden fixtures pass. Salinity/fertility use multiplicative stress on biomass increment (documented simplification; avoid double counting with transpiration pathway).
Soil carbon: carbon accounting reports tC and tCO2e for decisions, not credits.
Agrivoltaics: the largest scientific uncertainty. Always recommend a trial strip and light measurements (ceptometer/lux meter) before capex; calibration module fits tau_eff and f_par from user measurements.
Small plots: edge effects, border plants, satellite mixed pixels and kilogram-scale yields make plot-level statistics noisy - pool across seasons and plots in the hierarchy.
