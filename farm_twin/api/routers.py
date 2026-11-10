"""
FILE: farm_twin/api/routers.py
PURPOSE: FastAPI service exposing the core to the UI and agents. Versioned under /api/v1; OpenAPI auto-generated; pydantic models from domain; auth via OIDC/JWT (RBAC from agents/governance).
ROUTES (all return provenance-bearing models):
  /properties, /properties/{id}/plots (CRUD; geometry GeoJSON in/out), /plots/{id}/state?date= (FarmState view), /plots/{id}/observations (POST idempotent, GET series),
  /uploads/soil-report (multipart -> ingestion pipeline -> IngestionResult needing confirmation), /uploads/{id}/confirm,
  /data/weather?lon&lat&start&end, /data/forecast, /quality/{plot_id} (issues + completeness),
  /simulate/season (POST: plot, crop, plan, n_weather) -> sim_run id (async job; GET /jobs/{id}), /scenarios (CRUD), /scenarios/{id}/run, /scenarios/compare,
  /optimize (POST) -> job -> Pareto frontier ; /voi/rank ; /recommendations/{id} ; /recommendations/{id}/approve|reject|modify (human only),
  /outcomes (POST) ; /calibration/status|history ; /models (registry, versions, validation status) ; /agent/chat (SSE stream of agent events + approval interrupts) ; /agent/threads/{id}/resume.
  Long jobs run in a worker queue (Celery/RQ or arq) with progress events; results stored in DB; idempotency keys on POST.
  Rate limits, request size limits (uploads 25 MB), content-type sniffing, virus scan hook for uploads, CORS allowlist, structured logging with request ids.
TESTS: contract tests from OpenAPI; auth/RBAC; idempotency; upload size limit.
"""

from typing import Any
from uuid import uuid4
import json
import logging
import os
import re
import time

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def create_app(service: Any = None):
    """Create the API boundary; authentication, queue, and persistence adapters are injected."""
    try:
        import asyncio
        import inspect

        from fastapi import FastAPI, HTTPException, UploadFile, File, Header, Request
        from fastapi.responses import JSONResponse
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError as exc:
        raise RuntimeError("FastAPI and python-multipart must be installed to run the API") from exc
    app = FastAPI(title="Farm Digital Twin API", version="1.0.0", openapi_url="/api/v1/openapi.json")
    origins = [item.strip() for item in os.environ.get("FARM_TWIN_CORS_ORIGINS", "").split(",") if item.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
        )
    logger = logging.getLogger("farm_twin.api")
    rate_window_s = 60.0
    max_requests = max(1, int(os.environ.get("FARM_TWIN_RATE_LIMIT_PER_MIN", "120")))
    request_history: dict[str, list[float]] = {}

    async def dispatch(request, operation: str, payload: dict[str, Any] | None = None):
        if service is None or not hasattr(service, "dispatch"):
            raise HTTPException(503, "application service is not configured")
        await authorize(request, operation, request.path_params)
        arguments = {
            "path": request.path_params,
            "query": dict(request.query_params),
            "payload": payload,
            "idempotency_key": request.headers.get("Idempotency-Key"),
        }
        try:
            method = service.dispatch
            if inspect.iscoroutinefunction(method):
                result = await method(operation, **arguments)
            else:
                result = await asyncio.to_thread(method, operation, **arguments)
            return await result if inspect.isawaitable(result) else result
        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            if status_code is not None:
                raise HTTPException(int(status_code), str(exc)) from exc
            raise

    async def authorize(request, operation: str, resource: dict[str, Any]):
        if service is None or not hasattr(service, "authorize"):
            raise HTTPException(503, "RBAC authorization adapter is not configured")
        decision = service.authorize(getattr(request.state, "principal", None), operation, resource)
        if inspect.isawaitable(decision):
            decision = await decision
        if not decision:
            raise HTTPException(403, "not authorized for this operation")

    @app.middleware("http")
    async def authenticate(request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > MAX_UPLOAD_BYTES:
            return JSONResponse(status_code=413, content={"detail": "request exceeds 25 MB"})
        client_key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        recent = [stamp for stamp in request_history.get(client_key, []) if now - stamp < rate_window_s]
        if len(recent) >= max_requests:
            return JSONResponse(status_code=429, content={"detail": "request rate limit exceeded"})
        recent.append(now)
        request_history[client_key] = recent
        request_id = request.headers.get("X-Request-ID", "")
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", request_id):
            request_id = str(uuid4())
        if request.url.path == "/api/v1/health" or request.url.path.endswith("/openapi.json"):
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        if service is None or not hasattr(service, "authenticate"):
            response = JSONResponse(status_code=503, content={"detail": "OIDC/JWT authentication adapter is not configured"})
            response.headers["X-Request-ID"] = request_id
            return response
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            response = JSONResponse(status_code=401, content={"detail": "Bearer token required"})
            response.headers["X-Request-ID"] = request_id
            return response
        principal = service.authenticate(authorization[7:])
        if inspect.isawaitable(principal):
            principal = await principal
        if principal is None:
            response = JSONResponse(status_code=401, content={"detail": "invalid or expired token"})
            response.headers["X-Request-ID"] = request_id
            return response
        request.state.principal = principal
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request failed", extra={"request_id": request_id})
            raise
        response.headers["X-Request-ID"] = request_id
        return response

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok", "service": "farm-twin"}

    async def forwarded(request: Request):
        payload = None
        if request.method in {"POST", "PUT", "PATCH"}:
            try:
                payload = await request.json()
            except Exception:
                payload = None
        operation = request.scope["route"].name
        return await dispatch(request, operation, payload)

    routes = [
        ("/api/v1/properties", "properties_list", ["GET"]),
        ("/api/v1/properties", "properties_create", ["POST"]),
        ("/api/v1/properties/{property_id}/plots", "plots_list", ["GET"]),
        ("/api/v1/properties/{property_id}/plots", "plots_create", ["POST"]),
        ("/api/v1/plots/{plot_id}/state", "plot_state", ["GET"]),
        ("/api/v1/plots/{plot_id}/observations", "observations_list", ["GET"]),
        ("/api/v1/plots/{plot_id}/observations", "observations_create", ["POST"]),
        ("/api/v1/uploads/{upload_id}/confirm", "soil_report_confirm", ["POST"]),
        ("/api/v1/data/weather", "weather_data", ["GET"]),
        ("/api/v1/data/forecast", "weather_forecast", ["GET"]),
        ("/api/v1/quality/{plot_id}", "quality_report", ["GET"]),
        ("/api/v1/jobs/{job_id}", "job_status", ["GET"]),
        ("/api/v1/scenarios", "scenarios_list", ["GET"]),
        ("/api/v1/scenarios", "scenarios_create", ["POST"]),
        ("/api/v1/scenarios/{scenario_id}", "scenario_get", ["GET"]),
        ("/api/v1/scenarios/{scenario_id}", "scenario_update", ["PATCH"]),
        ("/api/v1/scenarios/{scenario_id}", "scenario_delete", ["DELETE"]),
        ("/api/v1/scenarios/{scenario_id}/run", "scenario_run", ["POST"]),
        ("/api/v1/scenarios/compare", "scenarios_compare", ["POST"]),
        ("/api/v1/optimize", "optimize", ["POST"]),
        ("/api/v1/voi/rank", "voi_rank", ["POST"]),
        ("/api/v1/recommendations/{recommendation_id}", "recommendation_get", ["GET"]),
        ("/api/v1/recommendations/{recommendation_id}/approve", "recommendation_approve", ["POST"]),
        ("/api/v1/recommendations/{recommendation_id}/reject", "recommendation_reject", ["POST"]),
        ("/api/v1/recommendations/{recommendation_id}/modify", "recommendation_modify", ["POST"]),
        ("/api/v1/outcomes", "outcome_create", ["POST"]),
        ("/api/v1/calibration/status", "calibration_status", ["GET"]),
        ("/api/v1/calibration/history", "calibration_history", ["GET"]),
        ("/api/v1/models", "models_list", ["GET"]),
        ("/api/v1/reports/build", "report_build", ["POST"]),
        ("/api/v1/agent/threads/{thread_id}/resume", "agent_resume", ["POST"]),
    ]
    for path, operation, methods in routes:
        app.add_api_route(path, forwarded, methods=methods, name=operation)

    @app.post("/api/v1/agent/chat")
    async def agent_chat(request: Request, payload: dict[str, Any]):
        from fastapi.responses import StreamingResponse

        await authorize(request, "agent_chat", {})
        if service is None or not hasattr(service, "stream_agent"):
            raise HTTPException(503, "agent stream service is not configured")
        events = service.stream_agent(payload, request.state.principal)
        if hasattr(events, "__await__"):
            events = await events

        async def event_stream():
            async for event in events:
                yield f"data: {json.dumps(event, default=str)}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.post("/api/v1/simulate/season", status_code=202)
    async def simulate(
        request: Request,
        payload: dict[str, Any],
        idempotency_key: str | None = Header(default=None),
    ):
        if service is None or not hasattr(service, "submit_simulation"):
            raise HTTPException(503, "simulation service unavailable")
        if not idempotency_key:
            raise HTTPException(400, "Idempotency-Key is required")
        await authorize(request, "simulate", {})
        try:
            submit = service.submit_simulation
            result = await submit(payload, idempotency_key) if inspect.iscoroutinefunction(submit) else await asyncio.to_thread(
                submit, payload, idempotency_key
            )
            return await result if hasattr(result, "__await__") else result
        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            if status_code is not None:
                raise HTTPException(int(status_code), str(exc)) from exc
            raise

    @app.post("/api/v1/uploads/soil-report", status_code=202)
    async def soil_upload(request: Request, file: UploadFile = File(...)):
        if file.content_type not in {"application/pdf", "text/csv", "text/plain"}:
            raise HTTPException(415, "unsupported content type")
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "upload exceeds 25 MB")
        if file.content_type == "application/pdf" and not data.startswith(b"%PDF-"):
            raise HTTPException(415, "file content does not match PDF declaration")
        if file.content_type in {"text/csv", "text/plain"}:
            try:
                data.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise HTTPException(415, "text upload must be valid UTF-8") from exc
        scanner = getattr(service, "scan_upload", None)
        if scanner is not None:
            clean = scanner(data, file.filename, file.content_type)
            if hasattr(clean, "__await__"):
                clean = await clean
            if not clean:
                raise HTTPException(422, "upload rejected by malware scanning hook")
        if service is None or not hasattr(service, "ingest_soil_report"):
            raise HTTPException(503, "ingestion service unavailable")
        await authorize(request, "soil_report_upload", {})
        try:
            ingest = service.ingest_soil_report
            result = await ingest(file.filename, data, file.content_type) if inspect.iscoroutinefunction(ingest) else await asyncio.to_thread(
                ingest, file.filename, data, file.content_type
            )
            return await result if hasattr(result, "__await__") else result
        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            if status_code is not None:
                raise HTTPException(int(status_code), str(exc)) from exc
            raise

    return app
