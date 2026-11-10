"""
FILE: farm_twin/data/providers/base.py
PURPOSE: Provider abstraction so no scientific code is tied to one weather/soil/market/satellite vendor.

IMPLEMENT:
    class ProviderMeta(BaseModel): name, kind {WEATHER, SOIL, SATELLITE, MARKET, TARIFF, WATER, DEM}, license, attribution_text, spatial_res_m|None,
        temporal_res, history_start, update_frequency, latency_days, coverage_bbox|None, suitable_for_calibration: bool, suitable_for_validation: bool, notes
    class WeatherProvider(Protocol): fetch_daily(lon, lat, start, end, *, variables) -> WeatherFrame ; fetch_forecast(lon, lat, days) -> WeatherFrame ; meta
    class SoilProvider(Protocol): fetch_profile(lon, lat) -> SoilPrior (per layer mean + uncertainty + sources)
    class MarketProvider(Protocol): fetch_prices(commodity, market, start, end) -> list[PriceObservation]
    class SatelliteProvider(Protocol): search(polygon, t0, t1, max_cloud), read(scene, polygon)
    class TariffProvider(Protocol): get_schedule(state_code, consumer_category, on_date) -> TariffSchedule
    class ProviderRegistry: register(provider), get(kind, name=None), ranked(kind, lon, lat) (picks by coverage, then recency, then user preference)
    ALL providers must: (1) cache raw responses on disk keyed by (provider, request hash) with TTL, store the raw payload as a `dataset` row with sha256;
        (2) return values as Quantified with source=IMPORTED and dataset_id set; (3) never raise on partial data - return MISSING entries + quality_flags;
        (4) implement retry with exponential backoff (3 tries, jitter) and a circuit breaker; (5) work offline from cache when `providers.<name>.enabled=false`.
    WeatherFrame columns (canonical): date, tmax_c, tmin_c, rain_mm, rs_mj_m2, rh_mean_pct|None, tdew_c|None, u2_ms|None, et0_mm|None(provider-computed, NOT trusted over own FAO-56), plus per-column provenance.
    WIND: providers give 10 m wind; convert to 2 m with u2 = u_z * 4.87 / ln(67.8*z - 5.42) (FAO-56 eq. 47).
TESTS: contract tests run each provider against recorded fixtures (vcrpy); missing column -> MISSING not exception; wind conversion u10=3.0 -> u2=2.24 m/s.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
import json
import time
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from farm_twin.core.provenance import Quantified
from farm_twin.core.ids import input_hash


class ProviderKind(str, Enum):
    WEATHER = "WEATHER"
    SOIL = "SOIL"
    SATELLITE = "SATELLITE"
    MARKET = "MARKET"
    TARIFF = "TARIFF"
    WATER = "WATER"
    DEM = "DEM"


class ProviderMeta(BaseModel):
    name: str
    kind: ProviderKind
    license: str | None = None
    attribution_text: str | None = None
    spatial_res_m: float | None = None
    temporal_res: str | None = None
    history_start: date | None = None
    update_frequency: str | None = None
    latency_days: float | None = None
    coverage_bbox: tuple[float, float, float, float] | None = None
    suitable_for_calibration: bool = False
    suitable_for_validation: bool = False
    notes: str | None = None


class WeatherFrame(BaseModel):
    rows: list[dict[str, Any]]
    provenance: dict[str, list[Quantified[Any]]] = Field(default_factory=dict)
    quality_flags: list[str] = Field(default_factory=list)
    dataset_id: str | None = None


class WeatherProvider(Protocol):
    meta: ProviderMeta

    def fetch_daily(
        self, lon: float, lat: float, start: date, end: date, *, variables: list[str] | None = None
    ) -> WeatherFrame: ...
    def fetch_forecast(self, lon: float, lat: float, days: int) -> WeatherFrame: ...


class SoilProvider(Protocol):
    meta: ProviderMeta

    def fetch_profile(self, lon: float, lat: float) -> dict[str, Any]: ...


class MarketProvider(Protocol):
    meta: ProviderMeta

    def fetch_prices(self, commodity: str, market: str, start: date, end: date) -> list[dict[str, Any]]: ...


class ProviderRegistry:
    def __init__(self) -> None:
        self._items: dict[tuple[ProviderKind, str], Any] = {}

    def register(self, provider: Any) -> None:
        self._items[(provider.meta.kind, provider.meta.name)] = provider

    def get(self, kind: ProviderKind, name: str | None = None) -> Any:
        items = [p for (k, n), p in self._items.items() if k == kind and (name is None or n == name)]
        if not items:
            raise KeyError(f"no provider registered for {kind.value}/{name or '*'}")
        return items[0]

    def ranked(self, kind: ProviderKind, lon: float, lat: float) -> list[Any]:
        return [p for (k, _), p in self._items.items() if k == kind]


class ProviderCache:
    """Content-addressed raw-response cache; cached payloads support audit and replay."""

    def __init__(self, root: str | Path = "data/provider_cache", ttl_seconds: int = 86400):
        self.root = Path(root)
        self.ttl_seconds = ttl_seconds

    def fetch_json(self, provider: str, request: dict[str, Any], fetch: Any) -> tuple[dict[str, Any], str, bool]:
        key = input_hash({"provider": provider, "request": request})
        path = self.root / provider / f"{key}.json"
        if path.exists() and time.time() - path.stat().st_mtime <= self.ttl_seconds:
            envelope = json.loads(path.read_text(encoding="utf-8"))
            return envelope["payload"], envelope["sha256"], True
        payload = fetch()
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        import hashlib

        digest = hashlib.sha256(raw).hexdigest()
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_bytes(json.dumps({"payload": payload, "sha256": digest}, sort_keys=True, default=str).encode())
        temp.replace(path)
        return payload, digest, False


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, reset_after_seconds: int = 60):
        self.failure_threshold = failure_threshold
        self.reset_after_seconds = reset_after_seconds
        self.failures = 0
        self.opened_at: float | None = None

    def before_call(self) -> None:
        if self.opened_at is not None:
            if time.time() - self.opened_at < self.reset_after_seconds:
                raise RuntimeError("provider circuit is open")
            self.opened_at = None
            self.failures = 0

    def success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.opened_at = time.time()
