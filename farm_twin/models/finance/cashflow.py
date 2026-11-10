"""
FILE: farm_twin/models/finance/cashflow.py
PURPOSE: Financial engine: per-plot and property cashflows, NPV/IRR/payback/LCOE, risk metrics. Annual step (monthly optional for working-capital checks).

IMPLEMENT:
 1. Crop budget per plot-season: revenue = yield_t_ha * area_ha * price_inr_per_t (PRICE = scenario draw; use fresh vs dry basis consistently; price at farm gate = mandi modal - transport - commission (user params)); costs = seed + fertiliser + amendment + pesticide + labour (days*wage) + irrigation (water cost + pumping kWh*tariff) + machinery + insurance + interest on working capital + land lease if any. Everything per season with timing (month index) for monthly cashflow.
 2. PV project cashflow: year-0 capex; yearly revenue = self-consumed kWh*avoided tariff + exported kWh*export tariff (per TariffSchedule rules; net-metering banking logic: monthly net import/export, credit carry-forward with expiry) ; opex (cleaning, O&M % of capex, insurance), inverter replacement at year ~10-12 (cost % of capex), degradation (0.5 %/yr default), tax/depreciation optional (user switches), subsidies as explicit user-entered line items (never assumed).
 3. Agrivoltaic combined: crop revenue under panels (from coupling) + PV revenue; shared structure cost; extra labour/ machinery constraints (user parameter: reduced mechanisation).
 4. Metrics: NPV = sum_t CF_t/(1+r)^t ; IRR by Brent root-finder on [-0.99, 10] (return NaN with reason if no sign change); simple and discounted payback (linear interpolation within year); LCOE = (capex + sum PV(opex))/(sum PV(energy)) in INR/kWh with energy discounted at the same rate; benefit-cost ratio; equivalent annual annuity for comparing unequal horizons; minimum cash balance (monthly) and peak funding need.
 5. Real vs nominal: all inputs nominal INR with explicit inflation per series (default 5 % general, electricity tariff escalation 0-3 % user-set, crop price inflation = CPI); discount rate nominal; terminal/salvage value of assets.
 6. RISK: given N joint scenarios (weather x price x tariff) produce distribution of NPV; VaR_alpha, CVaR_alpha (expected NPV of worst (1-alpha) tail; use 0.80/0.90), probability(NPV<0), worst-year cash shortfall probability, downside deviation.
 7. SENSITIVITY: tornado (one-at-a-time +/-20 % on price, yield, capex, tariff, discount rate), Sobol (see uncertainty/sensitivity.py).
 8. Working-capital and credit: simple loan amortisation (EMI = P*r(1+r)^n/((1+r)^n-1) with monthly r), overdraft constraint; the optimiser consumes `budget_by_year`.
 OUTPUT: CashflowResult(series by year/month, kpis, assumptions list with provenance).
RULES: no hard-coded prices, tariffs or subsidies; missing economic inputs raise MissingDataError listing exactly what is needed; every report prints currency, price basis, horizon, discount rate.
TESTS: NPV/IRR vs textbook example (CF = -1000, 300x5, r=10 % -> NPV = 137.24; IRR = 15.24 %); EMI example; payback interpolation; CVaR of known discrete distribution.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np
from pydantic import BaseModel, Field


def npv(cashflows: Sequence[float], discount_rate: float) -> float:
    if discount_rate <= -1:
        raise ValueError("discount_rate must be greater than -1")
    return sum(float(cf) / (1 + discount_rate) ** t for t, cf in enumerate(cashflows))


def irr(
    cashflows: Sequence[float], low: float = -0.99, high: float = 10.0, tolerance: float = 1e-12, max_iter: int = 500
) -> float:
    values = list(map(float, cashflows))
    if not values or not (any(x < 0 for x in values) and any(x > 0 for x in values)):
        return math.nan
    f_low = npv(values, low)
    f_high = npv(values, high)
    if f_low * f_high > 0:
        return math.nan
    for _ in range(max_iter):
        mid = (low + high) / 2
        f_mid = npv(values, mid)
        if abs(f_mid) < tolerance or high - low < tolerance:
            return mid
        if f_low * f_mid <= 0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid
    return (low + high) / 2


def payback_year(cashflows: Sequence[float], discount_rate: float | None = None) -> float | None:
    values = list(map(float, cashflows))
    if len(values) < 2 or values[0] >= 0:
        return None
    cumulative = values[0]
    for year, cf in enumerate(values[1:], start=1):
        value = cf / (1 + discount_rate) ** year if discount_rate is not None else cf
        previous = cumulative
        cumulative += value
        if cumulative >= 0:
            return (year - 1) + (-previous / value) if value else float(year)
    return None


def lcoe(capex: float, annual_opex: Sequence[float], energy_kwh: Sequence[float], discount_rate: float) -> float:
    if len(annual_opex) != len(energy_kwh):
        raise ValueError("opex and energy series lengths differ")
    pv_cost = capex + sum(x / (1 + discount_rate) ** (i + 1) for i, x in enumerate(annual_opex))
    pv_energy = sum(x / (1 + discount_rate) ** (i + 1) for i, x in enumerate(energy_kwh))
    if pv_energy <= 0:
        raise ValueError("discounted generation must be positive")
    return pv_cost / pv_energy


def equivalent_annual_annuity(npv_value: float, discount_rate: float, years: int) -> float:
    if years <= 0:
        raise ValueError("years must be positive")
    if discount_rate == 0:
        return npv_value / years
    return npv_value * discount_rate / (1 - (1 + discount_rate) ** (-years))


def cvar_lower_tail(values: Sequence[float], alpha: float = 0.9) -> float:
    """Expected value of the worst (1-alpha) fraction, including partial discrete mass."""
    if not 0 < alpha < 1 or not values:
        raise ValueError("alpha must be in (0,1) and values non-empty")
    ordered = sorted(map(float, values))
    tail = (1 - alpha) * len(ordered)
    n = int(math.floor(tail))
    frac = tail - n
    total = sum(ordered[:n]) + (frac * ordered[n] if frac and n < len(ordered) else 0)
    return total / tail


def risk_metrics(npv_scenarios: Sequence[float], alpha: float = 0.9) -> dict[str, float]:
    values = np.asarray(npv_scenarios, dtype=float)
    return {
        "mean_npv": float(values.mean()),
        "var_lower": float(np.quantile(values, 1 - alpha)),
        "cvar_lower": cvar_lower_tail(values, alpha),
        "probability_negative": float(np.mean(values < 0)),
        "downside_deviation": float(np.sqrt(np.mean(np.minimum(values - values.mean(), 0) ** 2))),
    }


def emi(principal: float, annual_rate: float, years: int, payments_per_year: int = 12) -> float:
    n = years * payments_per_year
    rate = annual_rate / payments_per_year
    if principal < 0 or years <= 0 or annual_rate < 0:
        raise ValueError("invalid loan terms")
    if rate == 0:
        return principal / n
    return principal * rate * (1 + rate) ** n / ((1 + rate) ** n - 1)


def apply_net_metering(
    monthly_import_kwh: Sequence[float],
    monthly_export_kwh: Sequence[float],
    import_tariff_inr_kwh: float,
    export_tariff_inr_kwh: float,
    banking_months: int = 12,
) -> dict[str, float]:
    if len(monthly_import_kwh) != len(monthly_export_kwh):
        raise ValueError("monthly series lengths differ")
    credits = [0.0] * max(1, banking_months)
    bill = export_credit = 0.0
    for i, (imp, exp) in enumerate(zip(monthly_import_kwh, monthly_export_kwh)):
        credits = [0.0] + credits[:-1]
        net = imp - exp
        if net > 0:
            remaining = net
            # Consume oldest expiring credits first.
            for j in reversed(range(len(credits))):
                take = min(remaining, credits[j])
                credits[j] -= take
                remaining -= take
            bill += remaining * import_tariff_inr_kwh
        elif net < 0:
            credits[0] += -net
    expired = sum(credits)
    export_credit = expired * export_tariff_inr_kwh
    return {
        "bill_inr": bill,
        "expired_export_kwh": expired,
        "export_credit_inr": export_credit,
        "net_cost_inr": bill - export_credit,
    }


class CashflowResult(BaseModel):
    series: list[float]
    kpis: dict[str, float | None]
    assumptions: list[dict] = Field(default_factory=list)
    currency: str = "INR"


def evaluate_cashflows(cashflows: Sequence[float], discount_rate: float) -> CashflowResult:
    value = npv(cashflows, discount_rate)
    rate = irr(cashflows)
    return CashflowResult(
        series=list(map(float, cashflows)),
        kpis={
            "npv_inr": value,
            "irr": rate if math.isfinite(rate) else None,
            "simple_payback_year": payback_year(cashflows),
            "discounted_payback_year": payback_year(cashflows, discount_rate),
        },
        assumptions=[{"discount_rate": discount_rate, "currency": "INR"}],
    )
