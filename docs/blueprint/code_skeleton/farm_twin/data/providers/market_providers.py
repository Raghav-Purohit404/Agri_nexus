"""
FILE: farm_twin/data/providers/market_providers.py
PURPOSE: Prices and tariffs.

IMPLEMENT:
  AgmarknetProvider: daily mandi prices (modal/min/max in INR per quintal, arrivals) from the Government of India Agmarknet/data.gov.in resource (API key via env; VERIFY resource id and field names live).
      Convert INR/quintal -> INR/tonne (x10). Build PriceSeries per (commodity, nearest mandis). Keep ALL raw records (dataset rows).
  MspProvider: Minimum Support Price table (user-maintained CSV by crop-year; floor price for notified crops). Used as a LOWER-BOUND SCENARIO for price distributions, not as a forecast.
  FertiliserPriceProvider: urea/DAP/MOP maximum retail prices (regulated/maintained by user CSV) - tiny table, manual with effective dates.
  TariffProvider implementations: StateTariffTable (CSV: state, category, slab, energy_charge, fixed_charge, effective_from) + NetMeteringRule (export credit rate, banking period, cap) - Rajasthan values must be entered/verified by the user from the discom's current order; the code ships NO hard-coded tariffs.
  PriceScenarioGenerator.fit(series): log-price AR(1) with seasonal mean (monthly dummies) fitted on >= 5 years; simulate N paths; clip to [MSP floor if applicable, 5x]; correlation of yield-shocks with price (negative for local supply shocks) via a user-set rho parameter (default -0.3, flagged ESTIMATED).
TESTS: unit conversion; AR(1) simulation reproduces the sample mean/variance within 10% on a synthetic series.
"""
