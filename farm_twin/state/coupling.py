"""
FILE: farm_twin/state/coupling.py
PURPOSE: Explicit model-coupling registry and capability negotiation.

IMPLEMENT: Edge(source_model.output -> target_model.input, transform, lag_days). Registered edges (minimum set):
   weather -> reference_et ; reference_et -> crop ; microclimate -> reference_et/crop/soil_temperature ; soil_water.fluxes -> salinity, nutrients ; salinity.root_ece -> crop.Ks_sal ;
   nutrients.Ks_N,Ks_PK -> crop.dB ; crop.residue_C -> rothc.inputs ; rothc.SOC -> soil_properties(OM%) -> pedotransfer (annual) ; crop.irrigation_applied -> water_state.ledger -> finance ;
   crop.yield -> finance.revenue ; solar.energy -> finance ; ground_radiation -> crop_coupling -> (crop, et0, rothc).
   topological_order(edges, active_models) ; detect_cycles -> must be broken by an edge with lag_days >= 1 else raise.
   negotiate(required_processes, available_models) -> composition plan or raises CapabilityError listing the missing process (e.g. 'salinity requested but crop model lacks it and no salinity model registered').
TESTS: cycle detection; negotiation outputs expected composition; lag edge resolves salinity<->crop cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict, deque
from typing import Iterable


class CapabilityError(ValueError):
    pass


class CouplingCycleError(ValueError):
    pass


@dataclass(frozen=True)
class Edge:
    source_model: str
    source_output: str
    target_model: str
    target_input: str
    lag_days: int = 0
    transform: str | None = None


DEFAULT_EDGES = (
    Edge("weather", "daily", "reference_et", "weather"),
    Edge("reference_et", "et0", "crop", "et0"),
    Edge("soil_water", "fluxes", "salinity", "fluxes"),
    Edge("soil_water", "fluxes", "nutrients", "fluxes"),
    Edge("salinity", "root_ece", "crop", "salinity", lag_days=1),
    Edge("nutrients", "stress", "crop", "nutrient_stress", lag_days=1),
    Edge("crop", "residue_c", "rothc", "carbon_input"),
    Edge("solar", "energy", "finance", "energy"),
    Edge("crop", "yield", "finance", "revenue"),
)


def topological_order(edges: Iterable[Edge], active_models: Iterable[str]) -> list[str]:
    nodes = set(active_models)
    adj = defaultdict(set)
    indegree = {n: 0 for n in nodes}
    for e in edges:
        if (
            e.source_model in nodes
            and e.target_model in nodes
            and e.lag_days < 1
            and e.target_model not in adj[e.source_model]
        ):
            adj[e.source_model].add(e.target_model)
            indegree[e.target_model] += 1
    q = deque(sorted(n for n, d in indegree.items() if d == 0))
    order = []
    while q:
        n = q.popleft()
        order.append(n)
        for nxt in sorted(adj[n]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                q.append(nxt)
    if len(order) != len(nodes):
        raise CouplingCycleError("zero-lag model coupling cycle detected")
    return order


def negotiate(required_processes: Iterable[str], available_models: Iterable[str]) -> list[str]:
    available = set(available_models)
    required = list(required_processes)
    missing = [p for p in required if p not in available]
    if missing:
        raise CapabilityError("missing required models: " + ", ".join(sorted(missing)))
    return required
