"""Database-backed API application service for the Python-only first-edition API."""

from __future__ import annotations

from contextvars import ContextVar
from datetime import date, datetime, timezone
import json
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from farm_twin.api.jobs import PostgresJobQueue
from farm_twin.core.provenance import ValueSource
from farm_twin.db.models import (
    ApiIdempotencyORM, CalibrationRunORM, ObservationORM, PlotORM,
    PropertyORM, RecommendationORM, ScenarioORM, VariableDefORM,
)
from farm_twin.db.repositories import (
    ApprovalRepo, AuditRepo, ObservationRepo, OutcomeRepo, PlotRepo, PropertyRepo,
    RecommendationRepo,
)
from farm_twin.domain.property_plot import LandUse, Plot, Property
from farm_twin.domain.scenario import Scenario
from farm_twin.gis.plot_geometry import area_m2, pick_local_epsg, validate_plot


class APIServiceError(Exception):
    """Expected API failure that carries an HTTP status without leaking DB internals."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


class SQLApplicationService:
    """Application boundary; all writes are transaction-scoped and all science remains injected."""

    READ_ROLES = {"VIEWER", "FARMER", "AGRONOMIST_ADVISOR", "ADMIN"}

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        authenticate_token: Callable[[str], dict[str, Any] | None] | None = None,
        model_registry: Any | None = None,
        providers: dict[str, Any] | None = None,
        job_handlers: dict[str, Callable[..., Any]] | None = None,
        upload_ingestor: Callable[[str | None, bytes, str], dict[str, Any]] | None = None,
        upload_scanner: Callable[[bytes, str | None, str], bool] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.authenticate_token = authenticate_token
        self.model_registry = model_registry
        self.providers = providers or {}
        self.job_handlers = job_handlers or {}
        self.upload_ingestor = upload_ingestor
        self.upload_scanner = upload_scanner
        self._principal: ContextVar[dict[str, Any] | None] = ContextVar("farm_twin_principal", default=None)

    def authenticate(self, bearer_token: str) -> dict[str, Any] | None:
        if self.authenticate_token is None:
            return None
        principal = self.authenticate_token(bearer_token)
        if not principal or not principal.get("sub"):
            return None
        self._principal.set(principal)
        return principal

    def authorize(self, principal: Any, operation: str, resource: dict[str, Any]) -> bool:
        identity = principal if isinstance(principal, dict) else {}
        roles = set(identity.get("roles", []))
        if not roles.intersection(self.READ_ROLES):
            return False
        if operation in {"recommendation_approve", "recommendation_reject", "recommendation_modify"}:
            if not roles.intersection({"FARMER", "ADMIN"}):
                return False
        if operation.startswith("calibration_") and operation != "calibration_status" and "ADMIN" not in roles:
            return False
        if operation in {"properties_create", "plots_create", "observations_create", "outcome_create",
                         "scenarios_create", "scenario_update", "scenario_delete", "scenario_run",
                         "simulate", "optimize"} and not roles.intersection({"FARMER", "ADMIN", "AGRONOMIST_ADVISOR"}):
            return False
        permitted = identity.get("property_ids", [])
        property_id = resource.get("property_id")
        if not property_id and resource.get("plot_id"):
            with self.session_factory() as session:
                from sqlalchemy import select
                plot = session.scalar(select(PlotORM.property_id).where(PlotORM.id == self._uuid(resource["plot_id"])))
                property_id = str(plot) if plot else None
        if not property_id and resource.get("scenario_id"):
            with self.session_factory() as session:
                scenario = session.get(ScenarioORM, self._uuid(resource["scenario_id"]))
                property_id = str(scenario.property_id) if scenario else None
        if property_id and "*" not in permitted and property_id not in permitted and "ADMIN" not in roles:
            return False
        return True

    def scan_upload(self, data: bytes, filename: str | None, content_type: str) -> bool:
        if self.upload_scanner is None:
            return False
        return bool(self.upload_scanner(data, filename, content_type))

    def ingest_soil_report(self, filename: str | None, data: bytes, content_type: str) -> dict[str, Any]:
        if self.upload_ingestor is None:
            raise APIServiceError(503, "soil-report parser/storage adapter is not configured")
        return self.upload_ingestor(filename, data, content_type)

    def _tenant(self) -> str:
        principal = self._principal.get()
        if not principal:
            raise APIServiceError(401, "authenticated principal is unavailable")
        return str(principal["sub"])

    @staticmethod
    def _public_property(row: Any) -> dict[str, Any]:
        from geoalchemy2.shape import to_shape

        point = to_shape(row.ref_point)
        return {"id": f"property_{row.id}", "name": row.name, "country_iso": row.country_iso,
                "region_code": row.region_code, "tz": row.tz, "reference_point": [point.x, point.y],
                "crs_local_epsg": row.local_epsg, "currency": row.currency,
                "land_unit_factors": row.land_unit_factors}

    @staticmethod
    def _public_plot(row: Any) -> dict[str, Any]:
        from geoalchemy2.shape import to_shape
        from shapely.geometry import mapping

        return {"id": f"plot_{row.id}", "property_id": f"property_{row.property_id}", "name": row.name,
                "geometry": mapping(to_shape(row.geom)), "area_m2": row.area_m2,
                "eligible_uses": row.eligible_uses, "land_use_current": row.land_use}

    def dispatch(
        self,
        operation: str,
        *,
        path: dict[str, str],
        query: dict[str, str],
        payload: dict[str, Any] | None,
        idempotency_key: str | None,
    ) -> Any:
        """Handle synchronous, data-backed operations. Long scientific work is queued, never faked."""
        actor = self._tenant()
        body = payload or {}
        try:
            with self.session_factory() as session, session.begin():
                if idempotency_key and operation not in {"job_status", "recommendation_get", "models_list",
                                                         "properties_list", "plots_list", "observations_list"}:
                    request_hash = self._hash_request(operation, path, query, body)
                    cached = session.get(ApiIdempotencyORM, (actor, idempotency_key))
                    if cached is not None:
                        if cached.operation != operation or cached.request_hash != request_hash:
                            raise APIServiceError(409, "Idempotency-Key was reused for a different request")
                        return cached.response
                result = self._dispatch_tx(session, operation, path, query, body, idempotency_key, actor)
                if idempotency_key and operation not in {"job_status", "recommendation_get", "models_list",
                                                         "properties_list", "plots_list", "observations_list"}:
                    session.add(ApiIdempotencyORM(tenant_id=actor, key=idempotency_key, operation=operation,
                                                  request_hash=self._hash_request(operation, path, query, body),
                                                  response=self._jsonable(result)))
                return result
        except APIServiceError:
            raise
        except (ValueError, TypeError) as exc:
            raise APIServiceError(422, str(exc)) from exc

    def _dispatch_tx(
        self, session: Session, operation: str, path: dict[str, str], query: dict[str, str],
        body: dict[str, Any], idempotency_key: str | None, actor: str,
    ) -> Any:
        if operation == "properties_list":
            principal = self._principal.get() or {}
            roles = set(principal.get("roles", []))
            stmt = select(PropertyORM).order_by(PropertyORM.name)
            permitted = principal.get("property_ids", [])
            if "ADMIN" not in roles and "*" not in permitted:
                ids = [self._uuid(i) for i in permitted if i != "*"]
                from sqlalchemy import or_
                stmt = stmt.where(or_(PropertyORM.owner_id == actor, PropertyORM.id.in_(ids))) if ids else stmt.where(PropertyORM.owner_id == actor)
            return [self._public_property(row) for row in session.scalars(stmt)]
        if operation == "properties_create":
            item = Property.model_validate(body)
            lon, lat = item.reference_point
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise APIServiceError(422, "reference_point must be WGS84 longitude, latitude")
            item.crs_local_epsg = item.crs_local_epsg or pick_local_epsg(lon, lat)
            PropertyRepo(session).create(item, owner_id=actor)
            AuditRepo(session).append(actor, "property.create", "property", item.id, None,
                                      {"name": item.name, "country_iso": item.country_iso})
            return item.model_dump(mode="json")
        if operation in {"plots_list", "plots_create"}:
            property_id = path["property_id"]
            parent = session.get(PropertyORM, self._uuid(property_id))
            if parent is None:
                raise APIServiceError(404, "property not found")
            if operation == "plots_list":
                rows = session.scalars(select(PlotORM).where(PlotORM.property_id == parent.id).order_by(PlotORM.name))
                return [self._public_plot(row) for row in rows]
            from shapely.geometry import shape

            geometry_data = body.get("geometry")
            if isinstance(geometry_data, dict) and geometry_data.get("type") == "Feature":
                geometry_data = geometry_data.get("geometry")
            if not isinstance(geometry_data, dict):
                raise APIServiceError(422, "plot geometry must be GeoJSON Polygon")
            geometry = shape(geometry_data)
            siblings = []
            from geoalchemy2.shape import to_shape
            for row in session.scalars(select(PlotORM.geom).where(PlotORM.property_id == parent.id)):
                siblings.append(to_shape(row))
            issues = validate_plot(geometry, siblings)
            repaired = next((issue.get("repaired") for issue in issues
                             if issue.get("code") == "invalid_geometry_repaired"), None)
            if repaired is not None:
                geometry = repaired
                if geometry.geom_type != "Polygon":
                    raise APIServiceError(422, "self-intersection repair did not produce one Polygon")
                issues = validate_plot(geometry, siblings)
            fatal = [issue for issue in issues if issue.get("severity") == "ERROR"]
            if fatal:
                raise APIServiceError(422, f"plot geometry rejected: {fatal}")
            allowed = {LandUse(value) for value in body.get("eligible_uses", ["CROPLAND", "FALLOW"])}
            item = Plot(id=body.get("id") or f"plot_{uuid4()}", property_id=f"property_{parent.id}",
                        name=str(body["name"]), geometry=geometry, area_m2=area_m2(geometry),
                        eligible_uses=allowed,
                        land_use_current=LandUse(body.get("land_use_current", "CROPLAND")))
            PlotRepo(session).create(item)
            AuditRepo(session).append(actor, "plot.create", "plot", item.id, None,
                                      {"name": item.name, "area_m2": item.area_m2})
            return self._public_plot(session.get(PlotORM, self._uuid(item.id)))
        if operation in {"observations_list", "observations_create"}:
            plot_id = self._uuid(path["plot_id"])
            plot = session.get(PlotORM, plot_id)
            if plot is None:
                raise APIServiceError(404, "plot not found")
            if operation == "observations_list":
                rows = session.scalars(select(ObservationORM).where(
                    ObservationORM.plot_id == plot_id, ObservationORM.superseded_by.is_(None)
                ).order_by(ObservationORM.observed_at))
                return [self._public_observation(row) for row in rows]
            source = body.get("source")
            if source not in {ValueSource.MEASURED.value, ValueSource.IMPORTED.value}:
                raise APIServiceError(422, "observations must be MEASURED or IMPORTED")
            observed_at = datetime.fromisoformat(str(body["observed_at"]).replace("Z", "+00:00"))
            if observed_at.tzinfo is None:
                raise APIServiceError(422, "observed_at must include a timezone")
            variable = str(body["variable"])
            if session.get(VariableDefORM, variable) is None:
                raise APIServiceError(422, f"variable {variable!r} is not registered; register its canonical unit first")
            row = {"id": uuid4(), "plot_id": plot_id, "property_id": plot.property_id, "variable": variable,
                   "depth_top_m": body.get("depth_top_m"), "depth_bottom_m": body.get("depth_bottom_m"),
                   "observed_at": observed_at, "value": float(body["value"]), "unit": str(body["unit"]),
                   "source": source, "method": body.get("method"),
                   "dataset_id": self._uuid(body["dataset_id"]) if body.get("dataset_id") else None,
                   "uncertainty_sd": body.get("uncertainty_sd"), "quality_flags": body.get("quality_flags", [])}
            inserted = ObservationRepo(session, ObservationORM).insert_many([row])
            if not inserted:
                duplicate = session.scalar(select(ObservationORM).where(
                    ObservationORM.plot_id == plot_id, ObservationORM.variable == variable,
                    ObservationORM.observed_at == observed_at, ObservationORM.dataset_id == row["dataset_id"]
                ))
                if duplicate:
                    return self._public_observation(duplicate)
                raise APIServiceError(409, "observation conflicts with an existing unique key")
            AuditRepo(session).append(actor, "observation.create", "plot", path["plot_id"], None,
                                      {"variable": variable, "source": source})
            return {"id": str(row["id"]), "variable": variable, "value": row["value"], "unit": row["unit"],
                    "source": source, "observed_at": observed_at.isoformat()}
        if operation.startswith("scenarios_") or operation.startswith("scenario_"):
            return self._scenario(session, operation, path, body, actor, idempotency_key)
        if operation == "job_status":
            from farm_twin.db.models import AsyncJobORM
            row = session.get(AsyncJobORM, self._uuid(path["job_id"]))
            if row is None or (row.tenant_id != actor and "ADMIN" not in self._roles()):
                raise APIServiceError(404, "job not found")
            return {"job_id": str(row.id), "status": row.status, "attempts": row.attempts,
                    "result": row.result, "error": row.error}
        if operation == "recommendation_get":
            recommendation = RecommendationRepo(session).get_public(path["recommendation_id"])
            if recommendation is None:
                raise APIServiceError(404, "recommendation not found")
            return recommendation
        if operation in {"recommendation_approve", "recommendation_reject", "recommendation_modify"}:
            decision = {"recommendation_approve": "APPROVED", "recommendation_reject": "REJECTED",
                        "recommendation_modify": "MODIFIED"}[operation]
            recommendation_id = path["recommendation_id"]
            row = session.get(RecommendationORM, self._uuid(recommendation_id))
            if row is None:
                raise APIServiceError(404, "recommendation not found")
            approval_id = ApprovalRepo(session).record(
                recommendation_id, decided_by=actor, decision=decision,
                note=str(body.get("note", "")), token_hash=None,
            )
            previous_status = row.status
            row.status = decision
            AuditRepo(session).append(actor, f"recommendation.{decision.lower()}", "recommendation",
                                      recommendation_id, {"status": previous_status},
                                      {"status": decision, "approval_id": approval_id})
            return {"approval_id": approval_id, "recommendation_id": recommendation_id, "decision": decision}
        if operation == "outcome_create":
            if body.get("source") not in {ValueSource.MEASURED.value, ValueSource.IMPORTED.value}:
                raise APIServiceError(422, "outcomes must be MEASURED or IMPORTED records")
            observed_at = datetime.fromisoformat(str(body["observed_at"]).replace("Z", "+00:00"))
            if observed_at.tzinfo is None:
                raise APIServiceError(422, "observed_at must include a timezone")
            identifier = OutcomeRepo(session).record(
                variable=str(body["variable"]), observed_at=observed_at, value=float(body["value"]),
                unit=str(body["unit"]), intervention_id=body.get("intervention_id"),
                prediction_id=body.get("prediction_id"), predicted_mean=body.get("predicted_mean"),
            )
            return {"id": identifier, "source": body["source"], "observed_at": observed_at.isoformat()}
        if operation in {"calibration_status", "calibration_history"}:
            rows = list(session.scalars(select(CalibrationRunORM).order_by(CalibrationRunORM.created_at.desc()).limit(100)))
            history = [{"id": str(row.id), "model": row.model, "decision": row.decision,
                        "reason": row.reason, "created_at": row.created_at.isoformat() if row.created_at else None}
                       for row in rows]
            return {"status": "no_calibration_runs" if not rows else "history_available",
                    "history": history} if operation == "calibration_status" else history
        if operation == "models_list":
            if self.model_registry is None:
                return []
            return [info.model_dump(mode="json") for _, info in self.model_registry._models.values()]
        if operation in {"weather_data", "weather_forecast"}:
            provider = self.providers.get("weather")
            if provider is None:
                raise APIServiceError(503, "weather provider is not configured; no data were fabricated")
            return self._provider_weather(provider, operation, query)
        if operation == "quality_report":
            return self._quality(session, path["plot_id"])
        if operation == "scenarios_compare":
            ids = body.get("scenario_ids", [])
            rows = session.scalars(select(ScenarioORM).where(ScenarioORM.id.in_([self._uuid(i) for i in ids])))
            return {"scenario_ids": [str(row.id) for row in rows], "paired": True,
                    "status": "requires_simulation_results", "property_kpis": {}}
        raise APIServiceError(501, f"operation {operation!r} requires a scientific or integration adapter not configured")

    def _scenario(self, session: Session, operation: str, path: dict[str, str], body: dict[str, Any],
                  actor: str, idempotency_key: str | None) -> Any:
        property_id = body.get("property_id")
        identifier = path.get("scenario_id")
        row = session.get(ScenarioORM, self._uuid(identifier)) if identifier else None
        if operation in {"scenarios_list", "scenarios_create"} and operation == "scenarios_list":
            stmt = select(ScenarioORM).where(ScenarioORM.owner_id == actor).order_by(ScenarioORM.created_at.desc())
            return [self._public_scenario(item) for item in session.scalars(stmt)]
        if operation == "scenarios_create":
            if not property_id or session.get(PropertyORM, self._uuid(property_id)) is None:
                raise APIServiceError(422, "scenario requires an existing property_id")
            config = dict(body)
            config["id"] = config.get("id") or f"scenario_{uuid4()}"
            config.setdefault("seed", 0)
            config.setdefault("plan", {"interventions": []})
            config.setdefault("weather", {"kind": "HISTORICAL_REPLAY", "n": 1})
            scenario = Scenario.model_validate(config)
            data = scenario.model_dump(mode="json")
            orm = ScenarioORM(id=self._uuid(scenario.id), property_id=self._uuid(property_id), owner_id=actor,
                              name=scenario.name, config=data)
            session.add(orm)
            session.flush()
            return self._public_scenario(orm)
        if row is None or (row.owner_id != actor and "ADMIN" not in self._roles()):
            raise APIServiceError(404, "scenario not found")
        if operation == "scenario_get":
            return self._public_scenario(row)
        if operation == "scenario_update":
            merged = {**row.config, **body}
            updated = Scenario.model_validate(merged).model_dump(mode="json")
            row.config, row.name, row.updated_at = updated, updated["name"], datetime.now(timezone.utc)
            return self._public_scenario(row)
        if operation == "scenario_delete":
            session.delete(row)
            return {"deleted": True, "scenario_id": identifier}
        if operation == "scenario_run":
            return self._enqueue(session, actor, "scenario_run", {"scenario_id": identifier}, idempotency_key)
        raise APIServiceError(501, f"scenario operation {operation!r} is unavailable")

    @staticmethod
    def _public_scenario(row: Any) -> dict[str, Any]:
        return {"id": f"scenario_{row.id}", "property_id": f"property_{row.property_id}",
                "name": row.name, **row.config, "created_at": row.created_at.isoformat(),
                "updated_at": row.updated_at.isoformat()}

    def submit_simulation(self, payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        actor = self._tenant()
        with self.session_factory() as session, session.begin():
            return self._enqueue(session, actor, "simulate_season", payload, idempotency_key)

    def _enqueue(self, session: Session, tenant: str, kind: str, payload: dict[str, Any], key: str | None) -> dict[str, Any]:
        if not key:
            raise APIServiceError(400, "Idempotency-Key is required for queued work")
        return PostgresJobQueue(session).enqueue(tenant, kind, payload, key)

    @staticmethod
    def _uuid(value: str):
        from uuid import UUID
        try:
            return UUID(value.rsplit("_", 1)[-1])
        except (ValueError, AttributeError) as exc:
            raise APIServiceError(422, "identifier must be a UUID or typed UUID") from exc

    def _roles(self) -> set[str]:
        principal = self._principal.get() or {}
        return set(principal.get("roles", []))

    @staticmethod
    def _public_observation(row: Any) -> dict[str, Any]:
        return {"id": str(row.id), "plot_id": f"plot_{row.plot_id}" if row.plot_id else None,
                "variable": row.variable, "observed_at": row.observed_at.isoformat(), "value": row.value,
                "unit": row.unit, "source": row.source, "method": row.method,
                "uncertainty_sd": row.uncertainty_sd, "quality_flags": row.quality_flags}

    @staticmethod
    def _provider_weather(provider: Any, operation: str, query: dict[str, str]) -> Any:
        if operation == "weather_data":
            frame = provider.fetch_daily(float(query["lon"]), float(query["lat"]),
                                         date.fromisoformat(query["start"]), date.fromisoformat(query["end"]))
            return frame.model_dump(mode="json") if hasattr(frame, "model_dump") else frame
        forecast = getattr(provider, "fetch_forecast", None)
        if forecast is None:
            raise APIServiceError(503, "configured weather provider does not provide forecasts")
        frame = forecast(float(query["lon"]), float(query["lat"]), int(query.get("days", 14)))
        return frame.model_dump(mode="json") if hasattr(frame, "model_dump") else frame

    def _quality(self, session: Session, plot_id: str) -> dict[str, Any]:
        plot = session.get(PlotORM, self._uuid(plot_id))
        if plot is None:
            raise APIServiceError(404, "plot not found")
        observations = list(session.scalars(select(ObservationORM).where(ObservationORM.plot_id == plot.id,
                                                                           ObservationORM.superseded_by.is_(None))))
        observed = {row.variable for row in observations}
        # Variable registration describes data shape, not the requirements of
        # a selected model; do not infer a completeness score from the registry.
        return {"plot_id": plot_id, "observations_count": len(observations), "variables": sorted(observed),
                "completeness": None, "completeness_status": "UNSCORABLE_NO_MODEL_REQUIREMENTS",
                "issues": [], "validation_status": "NOT_SCIENTIFICALLY_VALIDATED"}

    @staticmethod
    def _hash_request(operation: str, path: dict[str, Any], query: dict[str, Any], body: dict[str, Any]) -> str:
        encoded = json.dumps({"operation": operation, "path": path, "query": query, "payload": body},
                             sort_keys=True, separators=(",", ":"), default=str)
        from hashlib import sha256
        return sha256(encoded.encode()).hexdigest()

    @classmethod
    def _jsonable(cls, value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return cls._jsonable(value.model_dump(mode="json"))
        if isinstance(value, dict):
            return {str(k): cls._jsonable(v) for k, v in value.items()}
        if isinstance(value, (tuple, list, set)):
            return [cls._jsonable(item) for item in value]
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return value
