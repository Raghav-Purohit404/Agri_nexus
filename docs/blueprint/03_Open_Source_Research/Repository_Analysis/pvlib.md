# pvlib - role: oracle + reference for PV chain
Verified public functions: solarposition (spa, ephemeris...), irradiance (get_total_irradiance, perez, erbs, extra radiation), clearsky (ineichen, haurwitz), temperature (sapm_cell, faiman, pvsyst_cell), pvsystem.pvwatts_dc, inverter.pvwatts, iam, tracking.singleaxis, shading, bifacial.infinite_sheds. Gap: no crop/agrivoltaic ground-radiation-for-crops model.
Spec: models/solar/pv_engine.py, layout_sizing.py; golden: tests/golden/pvlib_jodhpur_clearsky.json.
