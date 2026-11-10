"""Interactive, local, one-day FarmState demo built on the project modules.

All default weather and soil values are demonstration estimates. This is not a
farm recommendation, crop-yield forecast, or scientifically validated model.
The app makes one transparent ET0 + layered soil-water transition, an optional
clear-sky PV estimate, and a finance scenario using only user-entered prices.
"""

from __future__ import annotations

from datetime import date
import math

import pandas as pd

from farm_twin.core.ids import new_id
from farm_twin.core.provenance import Quantified, Uncertainty, estimated
from farm_twin.domain.crop_state import CropState, CropStatus
from farm_twin.domain.farm_state import FarmState, PlotState, PropertyState, WeatherDay
from farm_twin.domain.property_plot import LandUse, Plot, Property
from farm_twin.domain.soil_state import SoilLayer, SoilState
from farm_twin.models.et.reference_et import et0_fao56
from farm_twin.models.finance.cashflow import evaluate_cashflows
from farm_twin.models.solar.pv_engine import pvwatts_hourly
from farm_twin.models.soil.water_balance import DailyForcing, LayeredWaterBalance, WaterColumn, WaterLayer


def build_demo_state(
    *, area_m2: float, theta: float, date_today: date, crop_name: str, latitude: float, longitude: float,
) -> FarmState:
    """Construct the demo FarmState with explicit ESTIMATED provenance."""
    uncertainty = lambda sd: Uncertainty(kind="sd", sd=sd)
    def q(value: float, unit: str, sd: float) -> Quantified[float]:
        return estimated(value, unit, method="demo_scenario_input; not a farm observation",
                         parent_ids=[], uncertainty=uncertainty(sd), model_version="demo-1")

    property_obj = Property(name="Example Rajasthan property", country_iso="IN", region_code="IN-RJ",
                            reference_point=(longitude, latitude), tz="Asia/Kolkata", currency="INR", area_m2=area_m2)
    plot = Plot(property_id=property_obj.id, name="Example plot", geometry=None, area_m2=area_m2,
                eligible_uses={LandUse.CROPLAND, LandUse.FALLOW, LandUse.PV_GROUND, LandUse.AGRIVOLTAIC})
    layer = SoilLayer(
        top_m=0, bottom_m=0.3,
        sand_pct=q(60, "%", 15), silt_pct=q(25, "%", 10), clay_pct=q(15, "%", 8),
        bulk_density_g_cm3=q(1.45, "g/cm^3", 0.2), theta=q(theta, "m^3/m^3", 0.04),
        theta_wp=q(0.10, "m^3/m^3", 0.03), theta_fc=q(0.25, "m^3/m^3", 0.04),
        theta_sat=q(0.42, "m^3/m^3", 0.04), theta_dry=q(0.05, "m^3/m^3", 0.02),
        ksat_mm_day=q(30, "mm/day", 15), tau=q(0.35, "1/day", 0.2),
    )
    soil = SoilState(layers=[layer], curve_number=75, rew_mm=9)
    crop = CropState(crop_id=crop_name, variety=None, planting_date=date_today,
                     status=CropStatus.EMERGED, canopy_cover=0.45, cc_nostress=0.45,
                     root_depth_m=0.3, dap=30)
    state = FarmState(date=date_today, property=PropertyState(), plots={plot.id: PlotState(
        plot=plot, soil=soil, crop=crop, land_use=LandUse.CROPLAND)}, property_static=property_obj,
        meta={"created_by": "interactive-demo", "parameter_set_ids": {"demo": "example-assumptions-v1"}})
    state.validate_invariants()
    return state


def run_demo() -> None:
    import streamlit as st

    st.set_page_config(page_title="Farm Digital Twin · Interactive Demo", page_icon="🌾", layout="wide")
    st.title("Farm Digital Twin — interactive demo")
    st.warning(
        "Demonstration only. Default inputs are ESTIMATED examples, not Rajasthan farm data. "
        "No yield recommendation is produced; crop, soil, weather, and tariff inputs require local evidence."
    )
    with st.sidebar:
        st.header("Scenario inputs")
        day = st.date_input("Scenario date", date(2026, 11, 10))
        latitude = st.number_input("Latitude (°N)", value=26.2389, min_value=-90.0, max_value=90.0, format="%.4f")
        longitude = st.number_input("Longitude (°E)", value=73.0243, min_value=-180.0, max_value=180.0, format="%.4f")
        area = st.number_input("Example plot area (m²)", min_value=1.0, max_value=100000.0, value=1000.0, step=50.0)
        crop_name = st.selectbox("Crop label (no yield model run)", ["wheat", "millet", "mustard", "unspecified"])
        st.caption("Crop selection labels the state only; configured, locally validated crop parameters are not available here.")
        st.subheader("Weather · scenario estimates")
        tmax = st.slider("Maximum temperature (°C)", 15.0, 50.0, 32.0)
        tmin = st.slider("Minimum temperature (°C)", 0.0, 35.0, 18.0)
        rh = st.slider("Mean relative humidity (%)", 5.0, 100.0, 35.0)
        rs = st.slider("Solar radiation (MJ/m²/day)", 0.0, 35.0, 18.0)
        wind = st.slider("Wind at 2 m (m/s)", 0.0, 15.0, 2.0)
        rain = st.slider("Rain today (mm)", 0.0, 150.0, 0.0)
        st.subheader("Soil and management · assumptions")
        theta0 = st.slider("Initial volumetric soil water", 0.05, 0.42, 0.20, 0.01)
        irrigation = st.slider("Gross irrigation today (mm)", 0.0, 100.0, 0.0)
        efficiency = st.slider("Application efficiency", 0.1, 1.0, 0.8)
        kc = st.slider("Transpiration coefficient used for this demo", 0.0, 1.5, 0.75)
        st.caption("The coefficient is an editable scenario assumption, not a calibrated crop coefficient.")
        st.subheader("PV · optional")
        pv_kwp = st.number_input("PV capacity (kWp)", min_value=0.0, max_value=1000.0, value=0.0, step=0.5)
        tilt = st.slider("PV tilt (°)", 0.0, 60.0, 26.0)
        tariff = st.number_input("Electricity value (INR/kWh)", min_value=0.0, value=0.0, help="User-supplied scenario assumption; zero by default.")

    date_frame = pd.DataFrame({"date": [day], "tmax_c": [tmax], "tmin_c": [tmin],
                               "rh_mean_pct": [rh], "rs_mj_m2": [rs], "u2_ms": [wind]})
    et0_series = et0_fao56(date_frame, latitude, 200.0)
    et0 = float(et0_series.iloc[0])
    scenario_parent = "interactive-scenario-inputs"
    def weather_value(value: float, unit: str, relative_sd: float) -> Quantified[float]:
        return estimated(value, unit, method="user-entered demo scenario; not an observation",
                         parent_ids=[scenario_parent], uncertainty=Uncertainty(kind="sd", sd=abs(value) * relative_sd),
                         model_version="demo-1")

    state0 = build_demo_state(area_m2=area, theta=theta0, date_today=day, crop_name=crop_name,
                              latitude=latitude, longitude=longitude)
    et0_q = estimated(et0, "mm/day", method="FAO-56 Penman–Monteith from demo scenario inputs",
                      parent_ids=[scenario_parent], uncertainty=Uncertainty(kind="sd", sd=max(0.1, et0 * 0.15)),
                      model_version="fao56-demo-1")
    weather_state = WeatherDay(date=day, values={
        "tmax_c": weather_value(tmax, "degC", 0.1),
        "tmin_c": weather_value(tmin, "degC", 0.1),
        "rh_mean_pct": weather_value(rh, "%", 0.15),
        "rs_mj_m2": weather_value(rs, "MJ/m^2/day", 0.15),
        "u2_ms": weather_value(wind, "m/s", 0.2),
        "rain_mm": weather_value(rain, "mm", 0.25),
        "et0_mm_day": et0_q,
    })
    state0 = state0.model_copy(update={"weather_today": weather_state}, deep=True)
    plot_key, plot0 = next(iter(state0.plots.items()))
    layer = plot0.soil.layers[0]
    water = WaterColumn(layers=[WaterLayer(top_m=layer.top_m, bottom_m=layer.bottom_m,
                                           theta=theta0, theta_wp=float(layer.theta_wp.value),
                                           theta_fc=float(layer.theta_fc.value), theta_sat=float(layer.theta_sat.value),
                                           ksat_mm_day=float(layer.ksat_mm_day.value), tau=float(layer.tau.value))])
    forcing = DailyForcing(rain_mm=rain, et0_mm=et0, irrigation_gross_mm=irrigation,
                           irrigation_efficiency=efficiency, canopy_cover=plot0.crop.canopy_cover,
                           crop_transpiration_demand_mm=et0 * kc * plot0.crop.canopy_cover,
                           curve_number=75, rew_mm=9, kex=1.1)
    water_next, flux = LayeredWaterBalance().step(water, forcing)
    final_theta = float(water_next.layers[0].theta)
    next_layer = layer.model_copy(update={"theta": estimated(final_theta, "m^3/m^3",
        method="layered water-balance one-day transition", parent_ids=[state0.meta.state_id],
        uncertainty=Uncertainty(kind="sd", sd=0.05), model_version="l1-demo")})
    next_plot = plot0.model_copy(update={"soil": plot0.soil.model_copy(update={"layers": [next_layer]})}, deep=True)
    if next_plot.crop:
        next_crop = next_plot.crop.model_copy(update={
            "transpiration_cum_mm": next_plot.crop.transpiration_cum_mm + flux.transpiration_mm,
            "irrigation_cum_mm": next_plot.crop.irrigation_cum_mm + flux.irrigation_net_mm,
        })
        next_plot = next_plot.model_copy(update={"crop": next_crop}, deep=True)
    state1 = state0.model_copy(update={"date": day, "plots": {plot_key: next_plot},
        "meta": state0.meta.model_copy(update={"state_id": new_id("state"),
                                                "parent_state_id": state0.meta.state_id})}, deep=True)
    state1.validate_invariants()

    st.subheader("One-day FarmState transition")
    a, b, c, d = st.columns(4)
    a.metric("Reference ET₀", f"{et0:.2f} mm/day", help="FAO-56 Penman–Monteith using scenario inputs")
    b.metric("Runoff", f"{flux.runoff_mm:.2f} mm")
    c.metric("Actual transpiration", f"{flux.transpiration_mm:.2f} mm")
    d.metric("Soil water after step", f"{final_theta:.3f} m³/m³")
    st.caption(f"ET₀ provenance: {et0_q.prov.source.value} · equation: FAO-56 Penman–Monteith. "
               f"Layered water balance residual: {flux.residual_mm:.4g} mm.")
    st.json({"date": day.isoformat(), "property_id": state0.property_static.id, "plot_id": plot_key,
             "state_before": state0.meta.state_id, "state_after": state1.meta.state_id,
             "state_parent": state1.meta.parent_state_id, "soil_water_before": layer.theta.model_dump(mode="json"),
             "soil_water_after": next_layer.theta.model_dump(mode="json"),
             "weather_et0": et0_q.model_dump(mode="json"), "water_fluxes_mm": flux.model_dump(mode="json")})
    with st.expander("View complete FarmState before and after"):
        st.json({"before": state0.model_dump(mode="json"), "after": state1.model_dump(mode="json")})

    st.subheader("Optional clear-sky PV estimate")
    if pv_kwp > 0:
        hours = pd.date_range(pd.Timestamp(day, tz="Asia/Kolkata"), periods=24, freq="h")
        pv_weather = pd.DataFrame({"temp_air_c": [tmax if 10 <= h.hour <= 16 else tmin for h in hours],
                                   "wind_ms": [wind] * len(hours)}, index=hours)
        pv = pvwatts_hourly(pv_weather, latitude_deg=latitude, longitude_deg=longitude,
                            tilt_deg=tilt, pdc0_w=pv_kwp * 1000, pac0_w=pv_kwp * 1000)
        energy = float(pv.energy_kwh.sum())
        p1, p2 = st.columns(2)
        p1.metric("Estimated PV generation", f"{energy:.2f} kWh/day")
        p2.metric("Indicative energy value", f"₹{energy * tariff:.2f}/day")
        st.caption("Model-generated Haurwitz clear-sky irradiance; user temperature/wind; generic module/loss assumptions. Not a Jodhpur golden-fixture validation.")
        st.line_chart(pv[["poa_w_m2", "pac_w"]])
    else:
        st.info("Enter a PV capacity to calculate an illustrative clear-sky production day. No generation is assumed when capacity is zero.")

    st.subheader("Deterministic finance scenario")
    st.caption("Only explicit user inputs are used. Zero defaults are placeholders, not market prices or tariffs.")
    f1, f2, f3, f4, f5 = st.columns(5)
    with f1:
        crop_margin = st.number_input("Crop net cashflow per year (INR)", min_value=-1e9, value=0.0, step=10000.0)
    with f2:
        pv_capex = st.number_input("PV CAPEX (INR)", min_value=0.0, value=0.0, step=10000.0)
    with f3:
        pv_opex = st.number_input("PV OPEX/year (INR)", min_value=0.0, value=0.0, step=1000.0)
    with f4:
        annual_pv_value = st.number_input("PV net value/year (INR)", min_value=0.0, value=0.0,
                                          help="Enter a separate annual scenario estimate; the daily clear-sky result is not annualized.")
    with f5:
        discount = st.number_input("Discount rate", min_value=0.0, max_value=0.99, value=0.10, step=0.01)
    horizon = st.slider("Finance horizon (years)", 1, 20, 5)
    cashflows = [-pv_capex] + [crop_margin + annual_pv_value - pv_opex for _ in range(horizon)]
    finance = evaluate_cashflows(cashflows, discount)
    st.metric("Scenario NPV", f"₹{finance.kpis['npv_inr']:,.0f}")
    st.line_chart(pd.DataFrame({"annual_cashflow_inr": cashflows}))
    st.json({"cashflow_result": finance.model_dump(mode="json"), "assumption_status": "USER_SCENARIO_INPUTS",
             "scientific_validation": "NOT_ESTABLISHED"})

    st.subheader("Model and evidence status")
    st.markdown(
        "- **Observed farm data:** missing in this demo; nothing is labeled measured.\n"
        "- **Soil hydraulics and weather:** wide-uncertainty example estimates. Replace with plot soil reports and weather observations.\n"
        "- **Crop yield, nutrients, soil carbon, salinity, solar crop response:** not calculated in this one-day demo.\n"
        "- **Optimization and intervention approval:** not executed; this screen provides no recommendation.\n"
        "- **Calibration:** no parameter set is promoted from demo inputs."
    )


if __name__ == "__main__":
    run_demo()
