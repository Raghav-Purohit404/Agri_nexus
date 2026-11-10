"""
FILE: farm_twin/data/providers/soil_providers.py
PURPOSE: Regional soil priors (used ONLY to seed hierarchy levels / fill unmeasured layers as ESTIMATED; never to override a lab report).

IMPLEMENT:
  SoilGridsProvider: ISRIC SoilGrids 2.0 REST (author knowledge, VERIFY): GET https://rest.isric.org/soilgrids/v2.0/properties/query ?lon&lat&property=sand&property=silt&property=clay&property=phh2o&property=soc&property=bdod&property=cec&property=nitrogen&depth=0-5cm&depth=5-15cm&depth=15-30cm&depth=30-60cm&depth=60-100cm&depth=100-200cm&value=mean&value=Q0.05&value=Q0.95
      Returns integer-scaled values with a `d_factor` per property (e.g. clay in g/kg -> /10 = %, phh2o pH*10 -> /10, bdod cg/cm3 -> /100 = g/cm3, soc dg/kg -> /100 = %, cec mmol(c)/kg -> /10 = cmol(c)/kg): READ d_factor and unit_measure from the response; do not hard-code.
      Use Q0.05..Q0.95 to derive uncertainty (sd ~ (Q95-Q05)/3.29). 250 m resolution; known to be weak in arid India and for salinity -> flag "regional_prior_low_confidence_arid".
  IndianSoilHealthProvider: Soil Health Card portal data are not available as a stable open API (VERIFY). Implement a PARSER for the Soil Health Card PDF/CSV the user uploads (see data/ingestion/soil_report.py) and a district-level prior table loader (CSV in data_dir) for N/P/K/OC/pH class distributions.
  GroundwaterProvider: India-WRIS / CGWB groundwater level and quality datasets (station-based, seasonal) loaded from user-supplied downloads; returns depth-to-water, EC, and SAR when available as IMPORTED with station distance.
TESTS: d_factor scaling; uncertainty derivation; prior never overwrites MEASURED.
"""
