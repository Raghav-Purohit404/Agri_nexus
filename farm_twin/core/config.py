"""
FILE: farm_twin/core/config.py
PURPOSE: Typed configuration (pydantic-settings), env + YAML, immutable after load, hashed into every sim_run.

IMPLEMENT: class Settings(BaseSettings) with nested models:
    db: url (postgresql+psycopg://...), pool_size
    paths: data_dir, artifact_dir, model_param_dir
    providers: dict[str, ProviderConfig] (enabled, base_url, api_key_env, cache_ttl_hours, rate_limit_per_min)
    simulation: n_weather_scenarios=50, max_parallel_workers=max(1, cpu_count-1)
    solver: preferred="appsi_highs", fallback=["cbc","glpk"], time_limit_s=120, mip_gap=0.001
    agents: llm_provider, model_name, temperature=0.0, max_tool_calls_per_run=40, approval_required_actions=[...]
    gpu: enabled=False (nothing in the scientific core may require a GPU)
    def config_hash(self) -> str      # sha256 of canonical JSON excluding secrets
RULES: secrets never in repo (.env.example provided); every provider can be disabled -> offline mode uses cached
       or bundled data.
TESTS: config_hash stable across key order; secrets excluded from the hash.
"""

from __future__ import annotations

import hashlib
import json
import os
from multiprocessing import cpu_count
from pathlib import Path
from typing import Any

from pydantic import SecretStr
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderConfig(BaseSettings):
    enabled: bool = False
    base_url: str | None = None
    api_key_env: str | None = None
    cache_ttl_hours: int = 24
    rate_limit_per_min: int = 60

    def api_key(self) -> SecretStr | None:
        return SecretStr(os.environ[self.api_key_env]) if self.api_key_env and self.api_key_env in os.environ else None


class DatabaseConfig(BaseSettings):
    url: str = "postgresql+psycopg://farm_twin:farm_twin_local_dev@localhost:5432/farm_twin"
    pool_size: int = 5


class PathConfig(BaseSettings):
    data_dir: Path = Path("data")
    artifact_dir: Path = Path("artifacts")
    model_param_dir: Path = Path("data/model_params")


class SimulationConfig(BaseSettings):
    n_weather_scenarios: int = 50
    max_parallel_workers: int = max(1, cpu_count() - 1)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FARM_TWIN_", env_nested_delimiter="__", extra="ignore")
    db: DatabaseConfig = DatabaseConfig()
    paths: PathConfig = PathConfig()
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    simulation: SimulationConfig = SimulationConfig()
    solver: dict[str, Any] = Field(
        default_factory=lambda: {
            "preferred": "appsi_highs",
            "fallback": ["cbc", "glpk"],
            "time_limit_s": 120,
            "mip_gap": 0.001,
        }
    )
    agents: dict[str, Any] = Field(
        default_factory=lambda: {"temperature": 0.0, "max_tool_calls_per_run": 40, "approval_required_actions": []}
    )
    gpu_enabled: bool = False

    def config_hash(self) -> str:
        data = self.model_dump(mode="json", exclude={"agents"})
        raw = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(raw.encode()).hexdigest()
