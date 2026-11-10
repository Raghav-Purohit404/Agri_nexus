"""ASGI entry point; deployment supplies a trusted service factory explicitly.

Set ``FARM_TWIN_SERVICE_FACTORY=package.module:callable`` to a Python callable
that returns a configured SQLApplicationService (database session factory,
OIDC verifier, adapters and worker handlers). The default exposes health and
OpenAPI only; it never silently disables authentication or fabricates services.
"""

from __future__ import annotations

import importlib
import os

from farm_twin.api.routers import create_app


def _load_service():
    target = os.environ.get("FARM_TWIN_SERVICE_FACTORY")
    if not target:
        return None
    module_name, separator, attribute = target.partition(":")
    if not separator:
        raise RuntimeError("FARM_TWIN_SERVICE_FACTORY must be module:callable")
    factory = getattr(importlib.import_module(module_name), attribute)
    service = factory()
    if service is None:
        raise RuntimeError("configured service factory returned None")
    return service


app = create_app(_load_service())
