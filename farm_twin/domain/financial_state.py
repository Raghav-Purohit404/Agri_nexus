"""
FILE: farm_twin/domain/financial_state.py
PURPOSE: FinancialState: capital, prices, costs, cashflow ledger.

IMPLEMENT: Budget(available_capital_inr, borrowing_limit, interest_rate, planning_horizon_years=10, discount_rate (default 0.10, user editable, with scenario range 0.07-0.14)),
    PriceSeries(commodity, unit, history, forecast distribution), InputCostCatalog (seed, urea, DAP, MOP, FYM, gypsum, labour/day, diesel, electricity tariff, water),
    CashflowLedger(entries: date, category, amount_inr, plot_id|None, kind {ACTUAL, PLANNED, SIMULATED}), TariffSchedule(kind {NET_METERING, FEED_IN, SELF_CONSUME_ONLY, TOU}, rates, effective dates).
RULE: SIMULATED and ACTUAL entries are separate kinds and never summed unless the report says so.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from pydantic import BaseModel, Field, model_validator


class EntryKind(str, Enum):
    ACTUAL = "ACTUAL"
    PLANNED = "PLANNED"
    SIMULATED = "SIMULATED"


class TariffKind(str, Enum):
    NET_METERING = "NET_METERING"
    FEED_IN = "FEED_IN"
    SELF_CONSUME_ONLY = "SELF_CONSUME_ONLY"
    TOU = "TOU"


class Budget(BaseModel):
    available_capital_inr: float
    borrowing_limit: float = 0
    interest_rate: float = 0
    planning_horizon_years: int = 10
    discount_rate: float = 0.10

    @model_validator(mode="after")
    def values_valid(self) -> "Budget":
        if self.available_capital_inr < 0 or self.borrowing_limit < 0 or not 0 <= self.discount_rate < 1:
            raise ValueError("invalid budget or discount rate")
        return self


class PriceSeries(BaseModel):
    commodity: str
    unit: str
    history: list[dict] = Field(default_factory=list)
    forecast_distribution: dict = Field(default_factory=dict)


class InputCostCatalog(BaseModel):
    costs: dict[str, float] = Field(default_factory=dict)
    effective_date: date | None = None
    provenance: dict[str, dict] = Field(default_factory=dict)


class CashflowEntry(BaseModel):
    date: date
    category: str
    amount_inr: float
    plot_id: str | None = None
    kind: EntryKind
    currency: str = "INR"


class CashflowLedger(BaseModel):
    entries: list[CashflowEntry] = Field(default_factory=list)

    def total(self, *, kinds: set[EntryKind]) -> float:
        return sum(e.amount_inr for e in self.entries if e.kind in kinds)


class TariffSchedule(BaseModel):
    kind: TariffKind
    rates: dict[str, float]
    effective_from: date
    effective_to: date | None = None
    currency: str = "INR"


class FinancialState(BaseModel):
    budget: Budget | None = None
    prices: list[PriceSeries] = Field(default_factory=list)
    input_costs: InputCostCatalog = Field(default_factory=InputCostCatalog)
    cashflow: CashflowLedger = Field(default_factory=CashflowLedger)
    tariffs: list[TariffSchedule] = Field(default_factory=list)
