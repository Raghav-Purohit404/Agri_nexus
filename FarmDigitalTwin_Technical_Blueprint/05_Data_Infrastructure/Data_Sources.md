# Data sources (all unverified endpoints - see skeleton provider specs)
Weather: station CSV (highest trust), IMD gridded (file-based), NASA POWER, Open-Meteo (reanalysis, coarse).
Soil: lab reports (user), Soil Health Card, SoilGrids priors (weak in arid India).
Satellite: Sentinel-2 L2A via provider interface; plots smaller than a pixel -> mixed-pixel policy.
Markets: Agmarknet mandi prices, MSP table (user), fertiliser prices (user), tariff tables (user, no hard-coded values).
Water: well yield/level, water-quality test (EC, SAR, ions), rainfall for harvesting.
Each provider: caching, retries, raw payload stored with sha256, licence + attribution recorded.
