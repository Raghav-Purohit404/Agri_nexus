"""
FILE: farm_twin/db/repositories.py
PURPOSE: Repository layer (SQLAlchemy 2.x + GeoAlchemy2). No SQL outside this package.

IMPLEMENT: PropertyRepo, PlotRepo (create/update with area recomputed in local CRS; spatial queries: plots_within(bbox), neighbours(plot)),
    ObservationRepo (insert_many idempotent via the UNIQUE key; latest(plot, variable, depth), series(plot, variable, t0, t1); supersede() instead of UPDATE/DELETE),
    EstimateRepo, PredictionRepo (bulk COPY insert for ensembles), ParameterSetRepo (resolve_effective(model, plot_id) walks PLOT->FARM->REGIONAL->GENERIC
    returning merged params + a provenance chain), SimRunRepo, InterventionRepo, RecommendationRepo, CalibrationRepo, AuditRepo (append-only).
RULES: observations are append-only (corrections create a new row and set superseded_by); every write passes through core.provenance validation;
       repositories return pydantic domain objects, never ORM rows.
TESTS: use testcontainers-postgis; idempotent re-import of the same soil report creates zero new rows; resolve_effective merges levels correctly.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from uuid import UUID

from farm_twin.core.provenance import ValueSource

T = TypeVar("T")


class Repository(Generic[T]):
    """Small typed base; domain mapping stays at the repository boundary."""

    def __init__(self, session: Session, model: type[T]) -> None:
        self.session, self.model = session, model

    def get(self, identifier: Any) -> T | None:
        row = self.session.get(self.model, identifier)
        if row is None:
            return None
        mapper = getattr(self.model, "to_domain", None)
        if mapper is not None:
            return mapper(row)
        # Generic repositories expose detached values, never a live ORM object.
        return {column.key: getattr(row, column.key) for column in self.model.__table__.columns}  # type: ignore[return-value]

    def add(self, entity: T) -> T:
        self.session.add(entity)
        self.session.flush()
        return entity


def _uuid(value: str) -> UUID:
    return UUID(value.rsplit("_", 1)[-1])


class PropertyRepo(Repository):
    def __init__(self, session: Session) -> None:
        from farm_twin.db.models import PropertyORM

        super().__init__(session, PropertyORM)

    def create(self, item: Any, *, owner_id: str | None = None) -> Any:
        from geoalchemy2.shape import from_shape
        from shapely.geometry import Point

        orm = self.model(
            id=_uuid(item.id),
            name=item.name,
            owner_id=owner_id,
            country_iso=item.country_iso,
            region_code=item.region_code,
            tz=item.tz,
            ref_point=from_shape(Point(*item.reference_point), srid=4326),
            local_epsg=item.crs_local_epsg or 4326,
            currency=item.currency,
            land_unit_factors=item.land_unit_factors,
        )
        self.session.add(orm)
        self.session.flush()
        return item


class PlotRepo(Repository):
    def __init__(self, session: Session) -> None:
        from farm_twin.db.models import PlotORM

        super().__init__(session, PlotORM)

    def create(self, item: Any) -> Any:
        from geoalchemy2.shape import from_shape
        from farm_twin.gis.plot_geometry import area_m2

        geom = item.geometry
        area = area_m2(geom)
        orm = self.model(
            id=_uuid(item.id),
            property_id=_uuid(item.property_id),
            name=item.name,
            geom=from_shape(geom, srid=4326),
            area_m2=area,
            eligible_uses=[x.value for x in item.eligible_uses],
            land_use=item.land_use_current.value,
        )
        self.session.add(orm)
        self.session.flush()
        item.area_m2 = area
        return item

    def plots_within(self, bbox: tuple[float, float, float, float]) -> list[Any]:
        from geoalchemy2.functions import ST_MakeEnvelope, ST_Intersects
        from geoalchemy2.shape import to_shape
        from farm_twin.domain.property_plot import LandUse, Plot

        west, south, east, north = bbox
        envelope = ST_MakeEnvelope(west, south, east, north, 4326)
        rows = self.session.scalars(select(self.model).where(ST_Intersects(self.model.geom, envelope)))
        return [
            Plot(
                id=f"plot_{row.id}", property_id=f"property_{row.property_id}", name=row.name,
                geometry=to_shape(row.geom), area_m2=row.area_m2,
                eligible_uses={LandUse(value) for value in row.eligible_uses},
                land_use_current=LandUse(row.land_use),
            )
            for row in rows
        ]

    def neighbours(self, plot_id: str) -> list[tuple[str, float]]:
        from geoalchemy2 import Geography
        from geoalchemy2.functions import ST_Boundary, ST_CollectionExtract, ST_Intersection, ST_Length

        target = self.session.get(self.model, _uuid(plot_id))
        if target is None:
            return []
        shared = ST_CollectionExtract(ST_Intersection(ST_Boundary(self.model.geom), ST_Boundary(target.geom)), 2)
        stmt = select(
            self.model.id, ST_Length(shared.cast(Geography(geometry_type="LINESTRING", srid=4326))).label("length")
        ).where(self.model.property_id == target.property_id, self.model.id != target.id)
        return [
            (str(identifier), float(length or 0))
            for identifier, length in self.session.execute(stmt)
            if length and length > 0
        ]


class EstimateRepo(Repository):
    def __init__(self, session: Session, model: type[Any] | None = None) -> None:
        if model is None:
            from farm_twin.db.models import EstimateORM
            model = EstimateORM
        super().__init__(session, model)

    def insert_many(self, estimates: Iterable[dict[str, Any]]) -> int:
        from uuid import uuid4

        rows = list(estimates)
        values = []
        for row in rows:
            if row.get("source", "ESTIMATED") != "ESTIMATED":
                raise ValueError("estimate repository accepts ESTIMATED values only")
            if row.get("uncertainty_sd") is None or float(row["uncertainty_sd"]) < 0:
                raise ValueError("estimates require nonnegative uncertainty")
            item = dict(row)
            item.pop("source", None)
            item["id"] = _uuid(item["id"]) if item.get("id") else uuid4()
            if item.get("plot_id"):
                item["plot_id"] = _uuid(item["plot_id"])
            values.append(item)
        if values:
            self.session.execute(insert(self.model), values)
        return len(values)


class PredictionRepo(Repository):
    def __init__(self, session: Session, model: type[Any] | None = None) -> None:
        if model is None:
            from farm_twin.db.models import PredictionORM
            model = PredictionORM
        super().__init__(session, model)

    def insert_many(self, predictions: Iterable[dict[str, Any]]) -> int:
        from uuid import uuid4

        values = []
        for row in predictions:
            item = dict(row)
            item.pop("source", None)  # Predictions have their own table and provenance.
            item["id"] = _uuid(item["id"]) if item.get("id") else uuid4()
            for key in ("plot_id", "sim_run_id"):
                if item.get(key):
                    item[key] = _uuid(item[key])
            values.append(item)
        if values:
            self.session.execute(insert(self.model), values)
        return len(values)


class ParameterSetRepo(Repository):
    def __init__(self, session: Session, model: type[Any] | None = None) -> None:
        if model is None:
            from farm_twin.db.models import ParameterSetORM

            model = ParameterSetORM
        super().__init__(session, model)

    def resolve_effective(
        self, model: str, scope_ids: dict[str, str | None]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        merged: dict[str, Any] = {}
        chain = []
        for level in ("GENERIC", "REGIONAL", "FARM", "PLOT"):
            scope = scope_ids.get(level)
            stmt = select(self.model).where(
                self.model.model == model,
                self.model.level == level,
                self.model.status == "ACTIVE",
            )
            stmt = stmt.where(self.model.scope_id == (_uuid(scope) if scope else None))
            row = self.session.scalar(stmt.order_by(self.model.created_at.desc()).limit(1))
            if row is not None:
                merged.update(row.params)
                chain.append({"level": level, "id": str(row.id), "status": row.status})
        return merged, chain


class SimRunRepo(Repository):
    def __init__(self, session: Session, model: type[Any] | None = None) -> None:
        if model is None:
            from farm_twin.db.models import SimRunORM
            model = SimRunORM
        super().__init__(session, model)

    def start(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Persist immutable inputs and explicit run status before simulation work begins."""
        from uuid import uuid4
        from datetime import datetime, timezone

        row = self.model(id=uuid4(), started_at=datetime.now(timezone.utc), status="RUNNING", **metadata)
        self.session.add(row)
        self.session.flush()
        return {"id": str(row.id), "status": row.status, "started_at": row.started_at}

    def finish(self, run_id: str, *, status: str, error: dict[str, Any] | None = None) -> None:
        from datetime import datetime, timezone

        if status not in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            raise ValueError("finished run status must be SUCCEEDED, FAILED, or CANCELLED")
        row = self.session.get(self.model, _uuid(run_id))
        if row is None:
            raise KeyError(f"simulation run {run_id} does not exist")
        if row.status != "RUNNING":
            raise ValueError(f"cannot finish simulation run in {row.status!r} state")
        row.status, row.error, row.finished_at = status, error, datetime.now(timezone.utc)
        self.session.flush()


class InterventionRepo(Repository):
    def __init__(self, session: Session, model: type[Any] | None = None) -> None:
        if model is None:
            from farm_twin.db.models import InterventionORM
            model = InterventionORM
        super().__init__(session, model)

    def create(self, values: dict[str, Any]) -> dict[str, Any]:
        from uuid import uuid4
        from farm_twin.domain.interventions import Intervention
        from pydantic import TypeAdapter

        validated = TypeAdapter(Intervention).validate_python(values)
        data = validated.model_dump(mode="json")
        identifier = uuid4()
        row = self.model(id=identifier, plot_id=_uuid(validated.plot_id) if validated.plot_id else None,
                         kind=validated.kind, payload=data, proposed_by=validated.proposed_by,
                         status=validated.status.value, planned_date=validated.date)
        self.session.add(row)
        self.session.flush()
        return {"id": str(identifier), "kind": row.kind, "status": row.status}

    def mark_executed(self, intervention_id: str, actual_payload: dict[str, Any]) -> None:
        from datetime import date

        row = self.session.get(self.model, _uuid(intervention_id))
        if row is None:
            raise KeyError(f"intervention {intervention_id} does not exist")
        if row.status != "APPROVED":
            raise ValueError("only an approved intervention can be marked executed")
        row.status, row.actual_payload, row.executed_date = "EXECUTED", actual_payload, date.today()
        self.session.flush()


class RecommendationRepo(Repository):
    def __init__(self, session: Session, model: type[Any] | None = None) -> None:
        if model is None:
            from farm_twin.db.models import RecommendationORM

            model = RecommendationORM
        super().__init__(session, model)

    def create(self, recommendation: dict[str, Any]) -> dict[str, Any]:
        from uuid import uuid4

        row = self.model(id=uuid4(), **recommendation)
        self.session.add(row)
        self.session.flush()
        return {"id": str(row.id), "status": row.status, "summary": row.summary}

    def get_public(self, identifier: str) -> dict[str, Any] | None:
        row = self.session.get(self.model, _uuid(identifier))
        if row is None:
            return None
        return {
            "id": str(row.id),
            "created_at": row.created_at,
            "summary": row.summary,
            "expected": row.expected,
            "evidence_refs": row.evidence_refs,
            "assumptions": row.assumptions,
            "status": row.status,
        }


class ApprovalRepo(Repository):
    """Append approval decisions; decision rows are never updated or removed."""

    def __init__(self, session: Session, model: type[Any] | None = None) -> None:
        if model is None:
            from farm_twin.db.models import ApprovalORM
            model = ApprovalORM
        super().__init__(session, model)

    def record(self, recommendation_id: str, *, decided_by: str, decision: str,
               note: str | None = None, token_hash: str | None = None) -> str:
        from uuid import uuid4

        if decision not in {"APPROVED", "REJECTED", "MODIFIED"}:
            raise ValueError("approval decision must be APPROVED, REJECTED, or MODIFIED")
        if not decided_by.strip():
            raise ValueError("decided_by is required")
        row = self.model(id=uuid4(), recommendation_id=_uuid(recommendation_id), decided_by=decided_by,
                         decision=decision, note=note, token_hash=token_hash)
        self.session.add(row)
        self.session.flush()
        return str(row.id)


class OutcomeRepo(Repository):
    """Store observations of intervention outcomes separately from predictions."""

    def __init__(self, session: Session, model: type[Any] | None = None) -> None:
        if model is None:
            from farm_twin.db.models import OutcomeORM
            model = OutcomeORM
        super().__init__(session, model)

    def record(self, *, variable: str, observed_at: Any, value: float, unit: str,
               intervention_id: str | None = None, prediction_id: str | None = None,
               predicted_mean: float | None = None) -> str:
        from uuid import uuid4
        import math

        if not math.isfinite(value):
            raise ValueError("outcome value must be finite")
        if not variable or not unit:
            raise ValueError("outcome variable and unit are required")
        error = value - predicted_mean if predicted_mean is not None else None
        row = self.model(id=uuid4(), variable=variable, observed_at=observed_at, value=value, unit=unit,
                         intervention_id=_uuid(intervention_id) if intervention_id else None,
                         prediction_id=_uuid(prediction_id) if prediction_id else None, error=error)
        self.session.add(row)
        self.session.flush()
        return str(row.id)


class CalibrationRepo(Repository):
    def __init__(self, session: Session, model: type[Any] | None = None) -> None:
        if model is None:
            from farm_twin.db.models import CalibrationRunORM
            model = CalibrationRunORM
        super().__init__(session, model)

    def record(self, values: dict[str, Any]) -> str:
        """Append a calibration decision record; parameter promotion is a separate gated operation."""
        from uuid import uuid4
        row = self.model(id=uuid4(), **values)
        self.session.add(row)
        self.session.flush()
        return str(row.id)


class StateDeltaRepo(Repository):
    """Persist periodic snapshots and reconstructable FarmState records."""

    def __init__(self, session: Session, model: type[Any] | None = None) -> None:
        if model is None:
            from farm_twin.db.models import StateDeltaORM
            model = StateDeltaORM
        super().__init__(session, model)

    def append(self, state: Any, *, sim_run_id: str | None = None, snapshot: bool = False) -> str:
        import json

        def jsonable(value: Any) -> Any:
            if hasattr(value, "model_dump"):
                return jsonable(value.model_dump(mode="python"))
            if hasattr(value, "__geo_interface__"):
                return value.__geo_interface__
            if hasattr(value, "value") and not isinstance(value, (str, bytes)):
                return jsonable(value.value)
            if hasattr(value, "isoformat"):
                return value.isoformat()
            if isinstance(value, dict):
                return {str(key): jsonable(item) for key, item in value.items()}
            if isinstance(value, (list, tuple, set)):
                return [jsonable(item) for item in value]
            return value

        state_id = _uuid(state.meta.state_id)
        parent_id = _uuid(state.meta.parent_state_id) if state.meta.parent_state_id else None
        if not snapshot and parent_id is None:
            raise ValueError("a non-snapshot state must reference its parent state")
        state_payload = json.loads(json.dumps(jsonable(state), sort_keys=True, default=str))
        delta: dict[str, Any]
        if snapshot:
            delta = {"$snapshot": state_payload}
        else:
            previous = self.load_payload(str(parent_id))
            operations: list[dict[str, Any]] = []
            def escape(key: Any) -> str:
                return str(key).replace("~", "~0").replace("/", "~1")

            def compare(old: Any, new: Any, path: str) -> None:
                if isinstance(old, dict) and isinstance(new, dict):
                    for key in sorted(old.keys() - new.keys()):
                        operations.append({"op": "remove", "path": f"{path}/{escape(key)}"})
                    for key in sorted(new.keys() - old.keys()):
                        operations.append({"op": "set", "path": f"{path}/{escape(key)}", "value": new[key]})
                    for key in sorted(old.keys() & new.keys()):
                        compare(old[key], new[key], f"{path}/{escape(key)}")
                elif old != new:
                    operations.append({"op": "set", "path": path, "value": new})

            compare(previous, state_payload, "")
            delta = {"$ops": operations}
        row = self.model(id=state_id, sim_run_id=_uuid(sim_run_id) if sim_run_id else None,
                         state_date=state.date, parent_state_id=parent_id,
                         delta=delta, is_snapshot=snapshot)
        self.session.add(row)
        self.session.flush()
        return str(row.id)

    def load_payload(self, state_id: str) -> dict[str, Any]:
        from copy import deepcopy

        target_id = _uuid(state_id)
        chain: list[Any] = []
        cursor = self.session.get(self.model, target_id)
        seen: set[Any] = set()
        while cursor is not None:
            if cursor.id in seen:
                raise ValueError("cycle detected in state ancestry")
            seen.add(cursor.id)
            chain.append(cursor)
            if cursor.is_snapshot:
                break
            if cursor.parent_state_id is None:
                raise ValueError("state chain has no snapshot ancestor")
            cursor = self.session.get(self.model, cursor.parent_state_id)
        if not chain or not chain[-1].is_snapshot:
            raise KeyError(f"state {state_id} or its snapshot ancestor is missing")
        payload = chain[-1].delta.get("$snapshot")
        if not isinstance(payload, dict):
            raise ValueError("stored snapshot payload is malformed")
        for row in reversed(chain[:-1]):
            operations = row.delta.get("$ops")
            if not isinstance(operations, list):
                raise ValueError("stored state delta operations are malformed")
            payload = deepcopy(payload)
            for operation in operations:
                path = operation.get("path", "")
                keys = [part.replace("~1", "/").replace("~0", "~") for part in path.split("/")[1:]]
                if not keys:
                    if operation.get("op") != "set" or not isinstance(operation.get("value"), dict):
                        raise ValueError("invalid root state replacement")
                    payload = operation["value"]
                    continue
                parent = payload
                for key in keys[:-1]:
                    parent = parent[key]
                if operation.get("op") == "remove":
                    parent.pop(keys[-1], None)
                elif operation.get("op") == "set":
                    parent[keys[-1]] = operation["value"]
                else:
                    raise ValueError("unknown state delta operation")
        return payload

    def load_state(self, state_id: str) -> Any:
        from shapely.geometry import shape
        from farm_twin.domain.farm_state import FarmState

        payload = self.load_payload(state_id)
        for plot_state in payload.get("plots", {}).values():
            plot = plot_state.get("plot")
            if isinstance(plot, dict) and isinstance(plot.get("geometry"), dict):
                plot["geometry"] = shape(plot["geometry"])
        return FarmState.model_validate(payload)


class AuditRepo(Repository):
    def append(self, actor: str, action: str, entity: str, entity_id: str, before: dict[str, Any] | None,
               after: dict[str, Any] | None, model: type[Any] | None = None) -> None:
        if model is None:
            from farm_twin.db.models import AuditLogORM
            model = AuditLogORM
        self.session.add(model(actor=actor, action=action, entity=entity,
                               entity_id=_uuid(entity_id), before=before, after=after))
        self.session.flush()


class ObservationRepo:
    """Append-only observation insertion; ORM model is supplied by caller."""

    def __init__(self, session: Session, model: type[Any]) -> None:
        self.session, self.model = session, model

    def insert_many(self, observations: Iterable[dict[str, Any]]) -> int:
        rows = list(observations)
        if any(row.get("source") not in {ValueSource.MEASURED.value, ValueSource.IMPORTED.value} for row in rows):
            raise ValueError("observations accept MEASURED or IMPORTED values only")
        if not rows:
            return 0
        statement = insert(self.model).values(rows).on_conflict_do_nothing()
        result = self.session.execute(statement)
        return int(result.rowcount or 0)

    def latest(self, plot_id: str, variable: str, depth_top_m: float | None = None) -> Any | None:
        stmt = select(self.model).where(self.model.plot_id == _uuid(plot_id), self.model.variable == variable)
        if depth_top_m is not None:
            stmt = stmt.where(self.model.depth_top_m == depth_top_m)
        row = self.session.scalar(stmt.order_by(self.model.observed_at.desc()).limit(1))
        return self._domain_value(row) if row else None

    @staticmethod
    def _domain_value(row: Any) -> Any:
        from farm_twin.core.provenance import imported, measured

        factory = measured if row.source == ValueSource.MEASURED.value else imported
        return {
            "value": factory(
                row.value,
                row.unit,
                method=row.method or "unspecified",
                dataset_id=str(row.dataset_id) if row.dataset_id else None,
                observed_at=row.observed_at,
            )
            if factory is measured
            else factory(
                row.value,
                row.unit,
                method=row.method or "provider-import",
                dataset_id=str(row.dataset_id) if row.dataset_id else None,
                retrieved_at=row.observed_at,
            ),
            "variable": row.variable,
            "depth_top_m": row.depth_top_m,
            "depth_bottom_m": row.depth_bottom_m,
            "observed_at": row.observed_at,
        }

    def series(self, plot_id: str, variable: str, t0: Any, t1: Any) -> list[Any]:
        stmt = (
            select(self.model)
            .where(
                self.model.plot_id == _uuid(plot_id),
                self.model.variable == variable,
                self.model.observed_at >= t0,
                self.model.observed_at <= t1,
                self.model.superseded_by.is_(None),
            )
            .order_by(self.model.observed_at)
        )
        return [self._domain_value(row) for row in self.session.scalars(stmt)]

    def supersede(self, old_id: str, new_observation: dict[str, Any]) -> int:
        from uuid import uuid4

        old = self.session.get(self.model, UUID(old_id))
        if old is None or old.superseded_by is not None:
            return 0
        new_id = uuid4()
        row = dict(new_observation, id=new_id)
        inserted = self.insert_many([row])
        if inserted:
            old.superseded_by = new_id
            self.session.flush()
        return inserted
