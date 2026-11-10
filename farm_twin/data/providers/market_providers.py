"""
FILE: farm_twin/data/providers/market_providers.py
PURPOSE: Prices and tariffs.

IMPLEMENT:
  AgmarknetProvider: daily mandi prices (modal/min/max in INR per quintal, arrivals) from the Government of India Agmarknet/data.gov.in resource (API key via env; VERIFY resource id and field names live).
      Convert INR/quintal -> INR/tonne (x10). Build PriceSeries per (commodity, nearest mandis). Keep ALL raw records (dataset rows).
  MspProvider: Minimum Support Price table (user-maintained CSV by crop-year; floor price for notified crops). Used as a LOWER-BOUND SCENARIO for price distributions, not as a forecast.
  FertiliserPriceProvider: urea/DAP/MOP maximum retail prices (regulated/maintained by user CSV) - tiny table, manual with effective dates.
  TariffProvider implementations: StateTariffTable (CSV: state, category, slab, energy_charge, fixed_charge, effective_from) + NetMeteringRule (export credit rate, banking period, cap) - Rajasthan values must be entered/verified by the user from the discom's current order; the code ships NO hard-coded tariffs.
  PriceScenarioGenerator.fit(series): log-price AR(1) with seasonal mean (monthly dummies) fitted on >= 5 years; simulate N paths; clip to [MSP floor if applicable, 5x]; correlation of yield-shocks with price (negative for local supply shocks) via a user-set rho parameter (default -0.3, flagged ESTIMATED).
TESTS: unit conversion; AR(1) simulation reproduces the sample mean/variance within 10% on a synthetic series.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import httpx

from farm_twin.core.errors import MissingDataError
from farm_twin.data.providers.base import ProviderKind, ProviderMeta


class AgmarknetProvider:
    meta = ProviderMeta(
        name="agmarknet_data_gov_in",
        kind=ProviderKind.MARKET,
        license="Government Open Data licence; verify dataset terms on access",
        temporal_res="daily",
        suitable_for_calibration=True,
        notes="API resource identifier and schema require current data.gov.in confirmation",
    )

    def __init__(self, resource_id: str | None = None, api_key_env: str = "DATA_GOV_IN_API_KEY"):
        self.resource_id = resource_id or os.getenv("AGMARKNET_RESOURCE_ID")
        self.api_key = os.getenv(api_key_env)

    def fetch_prices(self, commodity: str, market: str, start: date, end: date) -> list[dict[str, Any]]:
        if not self.resource_id or not self.api_key:
            raise MissingDataError("Agmarknet requires a verified resource ID and data.gov.in API key")
        response = httpx.get(
            f"https://api.data.gov.in/resource/{self.resource_id}",
            params={
                "api-key": self.api_key,
                "format": "json",
                "filters[commodity]": commodity,
                "filters[market]": market,
                "filters[arrival_date]": f"{start:%d/%m/%Y}-{end:%d/%m/%Y}",
                "limit": 1000,
            },
            timeout=30,
        )
        response.raise_for_status()
        records = response.json().get("records", [])
        for row in records:
            for key in ("modal_price", "min_price", "max_price"):
                if key in row and row[key] not in (None, ""):
                    row[key + "_inr_per_tonne"] = float(row[key]) * 10
        return records


def load_msp_csv(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if not {"crop", "crop_year", "price_inr_per_quintal"}.issubset(frame.columns):
        raise ValueError("MSP CSV requires crop, crop_year, price_inr_per_quintal")
    frame["price_inr_per_tonne"] = frame["price_inr_per_quintal"] * 10
    frame["scenario_role"] = "lower_bound_only"
    return frame


def load_user_cost_csv(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"item", "unit", "price", "effective_from", "source"}
    if not required.issubset(frame.columns):
        raise ValueError(f"cost CSV missing columns: {sorted(required - set(frame.columns))}")
    return frame


def state_tariffs_from_csv(path: str | Path, state_code: str, consumer_category: str, on_date: date) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"state", "category", "slab", "energy_charge", "fixed_charge", "effective_from"}
    if not required.issubset(frame.columns):
        raise ValueError("tariff CSV schema is incomplete")
    frame["effective_from"] = pd.to_datetime(frame["effective_from"]).dt.date
    return frame[
        (frame.state == state_code) & (frame.category == consumer_category) & (frame.effective_from <= on_date)
    ].sort_values("effective_from")
