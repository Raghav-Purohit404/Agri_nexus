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
