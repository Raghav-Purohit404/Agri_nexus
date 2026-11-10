"""
FILE: farm_twin/domain/soil_state.py
PURPOSE: SoilState - everything the soil/water/carbon/nutrient/salinity models read and write, PER LAYER.

IMPLEMENT: class SoilLayer (all fields Quantified):
    top_m, bottom_m (layers default to 0.1 m compartments to 2.0 m; allow user layering from soil report horizons)
    sand_pct, silt_pct, clay_pct, bulk_density_g_cm3, om_pct or oc_pct, coarse_fragment_pct
    theta (current), theta_wp, theta_fc, theta_sat, theta_dry, ksat_mm_day, tau (drainage characteristic, see models/soil/water_balance.py)
    ph, ec_e_dSm (saturated-paste EC), ec_1to5, sar, esp_pct, cec_cmolc_kg, caco3_pct
    n_nitrate_kg_ha, n_ammonium_kg_ha, p_olsen_mg_kg, k_exch_mg_kg (or ammonium-acetate K), micro: zn, fe, mn, cu, b, s (mg/kg)
    salt_mass_kg_ha (derived/state), na_exch, ca_exch, mg_exch
    rothc_pools_tC_ha: {DPM,RPM,BIO,HUM,IOM}  (topsoil layer(s) only)
  class SoilState: layers: list[SoilLayer]; surface_storage_mm; water_table_depth_m|None;
    curve_number; rew_mm; evap_layer_depth_m; stage2_evaporation flag; w_surf; w_stage2   (evaporation state, see models/soil/water_balance.py)
    methods: total_available_water_mm(root_depth_m), depletion_mm(root_depth_m), soc_stock_tC_ha(depth), to_arrays() (vectorised views).
RULES: when only topsoil lab data exist, deeper layers are ESTIMATED by pedotransfer/regional priors with explicit uncertainty; never MEASURED.
TESTS: TAW for 1.0 m of loam equals sum over layers of 1000*(theta_fc-theta_wp)*dz.
"""

from __future__ import annotations


from pydantic import BaseModel, Field, model_validator

from farm_twin.core.provenance import Quantified


class SoilLayer(BaseModel):
    top_m: float
    bottom_m: float
    sand_pct: Quantified[float] | None = None
    silt_pct: Quantified[float] | None = None
    clay_pct: Quantified[float] | None = None
    bulk_density_g_cm3: Quantified[float] | None = None
    om_pct: Quantified[float] | None = None
    oc_pct: Quantified[float] | None = None
    coarse_fragment_pct: Quantified[float] | None = None
    theta: Quantified[float] | None = None
    theta_wp: Quantified[float] | None = None
    theta_fc: Quantified[float] | None = None
    theta_sat: Quantified[float] | None = None
    theta_dry: Quantified[float] | None = None
    ksat_mm_day: Quantified[float] | None = None
    tau: Quantified[float] | None = None
    ph: Quantified[float] | None = None
    ec_e_dSm: Quantified[float] | None = None
    ec_1to5: Quantified[float] | None = None
    sar: Quantified[float] | None = None
    esp_pct: Quantified[float] | None = None
    cec_cmolc_kg: Quantified[float] | None = None
    caco3_pct: Quantified[float] | None = None
    n_nitrate_kg_ha: Quantified[float] | None = None
    n_ammonium_kg_ha: Quantified[float] | None = None
    p_olsen_mg_kg: Quantified[float] | None = None
    k_exch_mg_kg: Quantified[float] | None = None
    micro: dict[str, Quantified[float]] = Field(default_factory=dict)
    salt_mass_kg_ha: Quantified[float] | None = None
    na_exch: Quantified[float] | None = None
    ca_exch: Quantified[float] | None = None
    mg_exch: Quantified[float] | None = None
    rothc_pools_tC_ha: dict[str, Quantified[float]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def layer_bounds(self) -> "SoilLayer":
        if self.top_m < 0 or self.bottom_m <= self.top_m:
            raise ValueError("soil layer requires 0 <= top_m < bottom_m")
        return self


class SoilState(BaseModel):
    layers: list[SoilLayer]
    surface_storage_mm: float = 0.0
    water_table_depth_m: float | None = None
    curve_number: float | None = None
    rew_mm: float | None = None
    evap_layer_depth_m: float = 0.15
    stage2_evaporation: bool = False
    w_surf: float = 0.0
    w_stage2: float = 0.0

    def _layers_to_depth(self, depth_m: float) -> list[tuple[SoilLayer, float]]:
        remaining = max(0.0, depth_m)
        result = []
        for layer in self.layers:
            thickness = min(layer.bottom_m - layer.top_m, remaining)
            if thickness > 0:
                result.append((layer, thickness))
                remaining -= thickness
            if remaining <= 0:
                break
        return result

    def total_available_water_mm(self, root_depth_m: float) -> float:
        return sum(
            1000 * (layer.theta_fc.value - layer.theta_wp.value) * dz
            for layer, dz in self._layers_to_depth(root_depth_m)
            if layer.theta_fc
            and layer.theta_fc.value is not None
            and layer.theta_wp
            and layer.theta_wp.value is not None
        )

    def depletion_mm(self, root_depth_m: float) -> float:
        return sum(
            1000 * (layer.theta_fc.value - layer.theta.value) * dz
            for layer, dz in self._layers_to_depth(root_depth_m)
            if layer.theta_fc and layer.theta_fc.value is not None and layer.theta and layer.theta.value is not None
        )

    def soc_stock_tC_ha(self, depth_m: float) -> float:
        total = 0.0
        for layer, dz in self._layers_to_depth(depth_m):
            pool_sum = sum(q.value or 0 for q in layer.rothc_pools_tC_ha.values())
            total += pool_sum * dz / (layer.bottom_m - layer.top_m)
        return total

    def to_arrays(self) -> dict[str, list[float | None]]:
        return {
            field: [getattr(layer, field).value if getattr(layer, field) else None for layer in self.layers]
            for field in ("theta", "theta_wp", "theta_fc", "theta_sat", "ksat_mm_day")
        }
