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

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, field
from typing import Any

from farm_twin.core.provenance import measured


@dataclass(frozen=True)
class ClarificationRequest:
    field: str
    question: str
    source_value: str | None = None


@dataclass
class IngestionResult:
    observations: list[dict[str, Any]] = field(default_factory=list)
    issues: list[dict[str, str]] = field(default_factory=list)
    clarifications: list[ClarificationRequest] = field(default_factory=list)
    confidence_per_field: dict[str, float] = field(default_factory=dict)
    dataset_id: str | None = None


ALIASES = {
    "ph": ["pH", "Soil pH", "pH (1:2.5)", "pH(1:2)"],
    "ec": ["EC", "Electrical conductivity", "EC (dS/m)", "EC (1:2)", "ECe"],
    "oc": ["OC", "Organic Carbon", "Org. C", "O.C. %"],
    "n": ["Available N", "Avail. Nitrogen", "N (kg/ha)"],
    "p": ["Available P", "Olsen P", "Bray P", "P2O5"],
    "k": ["Available K", "K2O", "Exchangeable K"],
    "sand": ["sand", "Sand %"],
    "silt": ["silt", "Silt %"],
    "clay": ["clay", "Clay %"],
}
UNIT_ALIASES = {"mmhos/cm": "dS/m", "mS/cm": "dS/m", "ppm": "mg/kg", "percent": "%"}


def detect_format(filename: str, content: bytes) -> str:
    suffix = filename.lower().rsplit(".", 1)[-1]
    if suffix == "csv":
        return "CSV"
    if suffix in {"xlsx", "xls"}:
        return "XLSX"
    if suffix == "pdf":
        return "PDF_TEXT" if b"/Font" in content[:100000] else "PDF_SCANNED"
    if suffix in {"png", "jpg", "jpeg", "tif", "tiff"}:
        return "IMAGE"
    raise ValueError("unsupported soil-report format")


def _decode_unit(text: str) -> str | None:
    import re

    match = re.search(r"\(([^()]*(?:%|ppm|mg/kg|dS/m|mS/cm|mmhos/cm|kg/ha)[^()]*)\)", text, flags=re.I)
    if not match:
        return None
    raw = match.group(1).strip()
    return UNIT_ALIASES.get(raw, raw)


def parse_csv(
    content: bytes,
    *,
    plot_id: str,
    observed_at: Any,
    lab_name: str,
    depth_interval_m: tuple[float, float] | None = None,
    units: dict[str, str] | None = None,
) -> IngestionResult:
    result = IngestionResult(dataset_id=hashlib.sha256(content).hexdigest())
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    for row in reader:
        for variable, names in ALIASES.items():
            source_name = next((name for name in names if name in row), None)
            if source_name is None or row[source_name] in (None, ""):
                continue
            try:
                value = float(row[source_name])
            except ValueError:
                result.issues.append({"severity": "ERROR", "code": "non_numeric", "variable": variable})
                continue
            unit = (units or {}).get(variable) or _decode_unit(source_name)
            if variable != "ph" and unit is None:
                result.clarifications.append(
                    ClarificationRequest(
                        field=f"{variable}.unit",
                        question="What unit was used by the laboratory?",
                        source_value=row[source_name],
                    )
                )
                continue
            if depth_interval_m is None:
                result.clarifications.append(
                    ClarificationRequest(
                        field=f"{variable}.depth", question="What sampled soil depth does this value represent?"
                    )
                )
                continue
            canonical = UNIT_ALIASES.get(unit, unit) if unit else "dimensionless"
            if variable == "ec" and canonical == "dS/m":
                pass
            q = measured(
                value, canonical, method=f"lab:{lab_name}", dataset_id=result.dataset_id, observed_at=observed_at
            )
            result.observations.append(
                {
                    "plot_id": plot_id,
                    "variable": variable,
                    "value": q,
                    "depth_top_m": depth_interval_m[0],
                    "depth_bottom_m": depth_interval_m[1],
                    "method": f"lab:{lab_name}",
                }
            )
            result.confidence_per_field[variable] = 1.0
    return result


def extract_text_tables(content: bytes, file_format: str) -> str:
    if file_format == "CSV":
        return content.decode("utf-8-sig")
    if file_format == "PDF_TEXT":
        import pdfplumber

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    if file_format in {"PDF_SCANNED", "IMAGE"}:
        import pytesseract
        from PIL import Image

        image = Image.open(io.BytesIO(content)) if file_format == "IMAGE" else None
        if image is None:
            raise NotImplementedError("scanned-PDF rasterization requires a configured Tesseract/Poppler pipeline")
        return pytesseract.image_to_string(image)
    raise ValueError(f"unsupported parser format {file_format}")
