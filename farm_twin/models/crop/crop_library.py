"""
FILE: farm_twin/models/crop/crop_library.py
PURPOSE: Versioned crop parameter library with provenance and a validation status per crop. Parameters are NEVER silently invented.

SCHEMA CropParams (pydantic) - names follow the reference implementation so golden tests can be loaded directly:
   crop_type {1 leafy,2 root/tuber,3 fruit/grain}, calendar_type {1 days, 2 GDD}, determinant (bool), n stages: emergence, max_rooting, senescence, maturity, hi_start, flowering, yield_form (days or GDD),
   tbase, tupp, gdd_method, plant_pop, seed_size (cm2 cover), cc0 (derived), ccx, cgc, cdc, kcb, fage, wp (g/m2 normalised), wpy, fsink?, hi0, dhi0, a_hi, b_hi, hi_ini(0.01), zmin, zmax, pct_zmin, max_rooting, fshape_r, sxtop, sxbot, p_up1..4, p_lo1..4, fshape_w1..3, aer, germ thresholds, tmax_hs, tmin_hs, fc_product (moisture of harvested product), salt (a,b), nitrogen (Nc a,b), rue, etc.
   Each parameter carries: value, unit, source {AQUACROP_LIBRARY, FAO_PUBLICATION, LOCAL_TRIAL, EXPERT_ELICITED, PLACEHOLDER}, confidence, valid_range, citation.
VERIFIED EXAMPLE (reference library, WHEAT, use as the fully-specified template and as a golden test): CCx 0.96, WP 15.0 g/m2, HI0 0.48, Zmax 1.5 m, Kcb 1.1, Tbase 0 C, Tupp 26 C (values read from the reference library dump in tests/golden/wheat_params.json; the plain 'Wheat' entry has its own CalendarType - read it from the JSON, the GDD variants are separate entries such as WheatGDD). Codex: load the remaining wheat parameters from a committed JSON fixture `tests/golden/wheat_params.json` that will be produced by the Codex task "extract golden fixtures" (run the reference AquaCrop-OSPy package ONCE in a throwaway virtualenv and dump `crop_params['Wheat']` and its default soil/weather example to JSON - a test fixture, NOT a runtime dependency).
   The reference library (dump in tests/golden/reference_crop_list.json) contains: Alfalfa, Barley, Cassava, Cotton, DryBean, Maize, PaddyRice, Potato, Quinoa, Sorghum, Soybean, SugarBeet, SugarCane, Sunflower, Tef, Tomato, Wheat (+ GDD/regional variants). It does NOT contain pearl millet, mustard, chickpea, cluster bean, cumin, groundnut, sesame or castor.
SENTINEL WARNING [VERIFIED in the dump]: in the reference library many fields (stage lengths, CGC, CDC, Emergence, Maturity...) hold -9.0, meaning 'not stored - derive from the default calendar/cover procedure at run time'. Do NOT treat -9 as a number: model it as Optional[float]=None with a documented derivation rule (see phenology_roots.py and canopy.py), and make the Codex 'extract golden fixtures' task also dump the DERIVED values (CGC, CDC, CC0, stage dates, HIGC, tLinSwitch, dHILinear) for Wheat on the Tunis season so the derivation code has numeric targets.

INDIAN-CROP COVERAGE PLAN (needed for Rajasthan arid pilot) - crops of interest: pearl millet (bajra), cluster bean (guar), moth bean, mung bean, mustard (rapeseed), wheat, barley, chickpea, cumin, groundnut, sesame, castor, cotton, sorghum, fodder (berseem, Sudan grass), vegetables, jojoba/aloe/ber (perennial - unsupported L1).
   For every crop NOT in the reference library, create an entry with status PLACEHOLDER where each parameter is derived by `analog_crop` (nearest crop in the library, e.g. pearl millet <- sorghum/maize C4 analog) with +/- uncertainty (wide) and `validated=False`. The system must REFUSE production recommendations (agent-visible flag `needs_calibration`) for crops whose parameters are placeholders unless the user overrides, and must show the user which parameters are placeholders. Local calibration (calibration/) and trial data upgrade them.
   Priority for Level 3 cross-check: pearl millet, sorghum, wheat, groundnut (a detailed process model engine exists for these - see dssat_adapter.py).
API: get_crop(crop_id, variety=None, hierarchy=...) -> CropParams (merged generic<-regional<-farm<-plot); list_crops(status=...); diff(params_a, params_b); validate(params) -> issues (e.g. ccx in (0,1], stage order monotone, p_up<p_lo).
TESTS: round trip; placeholder crop flagged; hierarchy merge precedence PLOT > FARM > REGIONAL > GENERIC; wheat golden params load and simulate.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from farm_twin.core.errors import MissingDataError


class CropParams(BaseModel):
    crop_id: str
    variety: str | None = None
    status: str = "SUPPORTED_REFERENCE"
    validated: bool = False
    source: str = "AQUACROP_LIBRARY"
    parameters: dict[str, float | None] = Field(default_factory=dict)
    units: dict[str, str] = Field(default_factory=dict)
    confidence: dict[str, float | None] = Field(default_factory=dict)
    citation: str | None = None
    overrides_by_level: dict[str, dict[str, float]] = Field(default_factory=dict)
    needs_calibration: bool = True

    @model_validator(mode="after")
    def placeholder_status(self) -> "CropParams":
        if self.status == "PLACEHOLDER":
            self.validated = False
            self.needs_calibration = True
        return self


def _load_wheat() -> CropParams:
    path = Path(__file__).resolve().parents[3] / "tests" / "golden" / "wheat_params.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    parameters: dict[str, float | None] = {}
    for name, value in raw.items():
        if isinstance(value, (int, float)):
            parameters[name] = None if float(value) == -9 else float(value)
    return CropParams(
        crop_id="wheat",
        parameters=parameters,
        status="REFERENCE_PARAMS_UNVALIDATED",
        validated=False,
        citation="tests/golden/wheat_params.json; source reference dump",
    )


_CROPS = {"wheat": _load_wheat()}
_INDIAN_PLACEHOLDERS = (
    "pearl_millet",
    "cluster_bean",
    "moth_bean",
    "mung_bean",
    "mustard",
    "chickpea",
    "cumin",
    "groundnut",
    "sesame",
    "castor",
    "berseem",
    "sudan_grass",
)
for _name in _INDIAN_PLACEHOLDERS:
    _CROPS[_name] = CropParams(
        crop_id=_name,
        status="PLACEHOLDER",
        source="PLACEHOLDER",
        parameters={},
        citation="No locally validated parameter set supplied",
    )


def get_crop(
    crop_id: str,
    variety: str | None = None,
    hierarchy: dict[str, dict[str, float]] | None = None,
    *,
    allow_placeholder: bool = False,
) -> CropParams:
    key = crop_id.lower().replace(" ", "_")
    if key not in _CROPS:
        raise KeyError(f"crop {crop_id!r} is not in the declared crop library")
    crop = _CROPS[key].model_copy(deep=True)
    crop.variety = variety
    crop.overrides_by_level = hierarchy or {}
    for level in ("REGIONAL", "FARM", "PLOT"):
        crop.parameters.update(crop.overrides_by_level.get(level, {}))
    if crop.status == "PLACEHOLDER" and not allow_placeholder:
        raise MissingDataError(
            "Crop has placeholder parameters and cannot be simulated for production",
            context={"crop": key, "needs_calibration": True},
        )
    return crop


def list_crops(status: str | None = None) -> list[CropParams]:
    return [v.model_copy(deep=True) for v in _CROPS.values() if status is None or v.status == status]


def diff(params_a: CropParams, params_b: CropParams) -> dict[str, tuple[float | None, float | None]]:
    keys = set(params_a.parameters) | set(params_b.parameters)
    return {
        k: (params_a.parameters.get(k), params_b.parameters.get(k))
        for k in sorted(keys)
        if params_a.parameters.get(k) != params_b.parameters.get(k)
    }


def validate(params: CropParams) -> list[str]:
    issues = []
    p = params.parameters
    if p.get("CCx") is not None and not 0 < p["CCx"] <= 1:
        issues.append("CCx must be in (0,1]")
    for top, low in (("p_up1", "p_lo1"), ("p_up2", "p_lo2"), ("p_up3", "p_lo3"), ("p_up4", "p_lo4")):
        if p.get(top) is not None and p.get(low) is not None and p[top] >= p[low]:
            issues.append(f"{top} must be less than {low}")
    return issues
