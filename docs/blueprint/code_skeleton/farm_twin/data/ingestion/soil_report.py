"""
FILE: farm_twin/data/ingestion/soil_report.py
PURPOSE: Turn an uploaded soil lab report (PDF, scanned image, CSV, XLSX, Soil Health Card) into validated per-plot SoilLayer observations. NEVER fabricate.

PIPELINE (implement each stage as a pure function returning a typed result + issue list):
  1. detect_format(file) -> {CSV, XLSX, PDF_TEXT, PDF_SCANNED, IMAGE}
  2. extract_text_tables: pdfplumber for text PDFs; for scans use OCR (pytesseract) - OCR output is ALWAYS marked low-confidence and requires user confirmation of every numeric field.
  3. field_mapper: map lab-specific names to canonical variables through an alias table (YAML, extensible):
        pH: ["pH","Soil pH","pH (1:2.5)","pH(1:2)"] ; EC: ["EC","Electrical conductivity","EC (dS/m)","EC (1:2)","ECe"] ; OC: ["OC","Organic Carbon","Org. C","O.C. %"] ;
        N: ["Available N","Avail. Nitrogen","N (kg/ha)"] ; P: ["Available P","Olsen P","Bray P","P2O5"] ; K: ["Available K","K2O","Exchangeable K"] ; micro: Zn, Fe, Mn, Cu, B, S ; texture: sand/silt/clay or class name ; CEC, ESP, SAR, CaCO3, bulk density
  4. method_capture: record the extraction method per variable (P: Olsen vs Bray vs Mehlich; K: NH4OAc; N: alkaline permanganate (KMnO4) is an INDEX not mineral N) -
        store in `method`; downstream models must check method compatibility before use (e.g. Olsen-P thresholds differ from Bray-P).
  5. unit_normalise using core.units (kg/ha vs mg/kg vs ppm; % vs g/kg; mmhos/cm == dS/m). If a value has an ambiguous unit, STOP and emit a ClarificationRequest (do not guess).
  6. depth_detect: depth interval from text ("0-15 cm"); default NOT assumed: if absent -> ClarificationRequest.
  7. validate: core.units.validate_range; texture sum check (sand+silt+clay = 100 +/- 2); pH/EC consistency (flag EC>4 with pH>8.5 as likely saline-sodic); duplicates (same plot/date/depth/variable).
  8. texture_class: USDA triangle classification from sand/silt/clay (implement the 12-class boundaries) when only fractions are given; if only class given, return ESTIMATED sand/silt/clay at class centroid with +/- class half-range uncertainty.
  9. persist as observations (MEASURED, method="lab:<lab name>", dataset_id=file sha) - one report per plot; link report date; staleness rule: soil test older than 3 years -> flag `stale` (OC/pH/EC) ; nutrient tests older than 1 crop season flagged for N.
OUTPUT: IngestionResult(observations, issues[ERROR|WARN|INFO], clarifications[], confidence_per_field).
TESTS: sample CSV/PDF fixtures; ambiguous unit -> ClarificationRequest; texture class centroid for "sandy loam" returns sand ~ 65 +/- 12 % flagged ESTIMATED.
"""
