"""
FILE: farm_twin/models/solar/layout_sizing.py
PURPOSE: Turn plot geometry + PV config into capacity, rows, spacing, and shading-aware yield; tiny plots (55-120 m2) mean single-digit kWp systems.

IMPLEMENT:
  fixed-tilt row geometry: collector slant width Wc, tilt beta -> horizontal footprint w = Wc*cos(beta), height rise h = Wc*sin(beta); pitch P; GCR = Wc/P (ratio of collector width to pitch).
  row-to-row shading limit: minimum pitch to avoid shading at winter-solstice 9:00-15:00 solar time: P_min = Wc*(cos(beta) + sin(beta)/tan(alpha_s)) with alpha_s = sun elevation at the limiting hour (compute from solar position, not a fixed 'rule').
  fit_rows(plot_polygon_local, azimuth, Wc, beta, P, edge_setback): place rows along the long axis perpendicular to azimuth inside the setback-buffered polygon (shapely); modules per row = floor(row_length/module_width) * modules per collector; kWp = n_modules*module_Wp/1000.
  electrical sizing basics: DC/AC ratio 1.1-1.3 (default 1.2), string voltage within inverter MPPT window using Voc temperature correction (module params) - implement as checks returning issues, NOT an electrical design deliverable; code requires the user to confirm with a licensed installer.
  shading-aware yield: for each hour compute row-to-row shaded fraction (shadow overlap length on the next row: s = max(0, 1 - ((P - w)*... geometry) - implement via 2D projection of shadow edge using sun azimuth/elevation in the row-normal plane) and reduce POA beam by shaded fraction on the electrically-affected strings (assume bypass-diode granularity: each cell string loses proportionally in steps of n_substrings); diffuse unaffected except sky view factor reduction.
  tracker (single-axis N-S): rotation angle by astronomical tracking with backtracking (standard closed-form: tan(theta) = sin(z)sin(az - axis_az)/(cos(z)...) - implement from published single-axis tracking equations) - only as optional config; not default for tiny plots.
  CAPEX/OPEX hooks to finance/costs.py: capex = n_kWp*cost_per_kWp + structure + inverter + BoS + installation; elevated agrivoltaic structures cost more (user input; no hard-coded national price).
TESTS: GCR relation; P_min at beta=20 deg, Wc=2 m, alpha_s=25 deg => 2*(0.9397 + 0.3420/0.4663) = 3.35 m; rows fit count for a 10 m x 7.5 m plot.
"""
