# AquaCrop-OSPy - what to implement from it (spec summary)
Strengths: water-driven yield, canopy cover, two-stage evaporation, curve-number runoff, tau-based drainage, root growth, stress coefficients, harvest-index build-up, irrigation policies. Weaknesses for this project: no salinity, fertility, weeds, perennials; light/temperature effects limited; crop library missing Indian arid crops.
Spec locations: canopy.py, stress.py, transpiration_biomass_hi.py, phenology_roots.py, soil/water_balance.py, soil/pedotransfer.py, crop/aquacrop_native.py.
Daily order (verified): see aquacrop_native.py docstring.
