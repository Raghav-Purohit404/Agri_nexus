"""Worker executable with deployment-provided scientific handlers.

``FARM_TWIN_WORKER_FACTORY=package.module:callable`` must return
``(session_factory, handlers)``. Handlers are at-least-once and must be
idempotent; absent handlers fail and retry jobs instead of returning mock data.
"""

from __future__ import annotations

import asyncio
import importlib
import os
import signal

from farm_twin.api.jobs import run_worker


async def serve() -> None:
    target = os.environ.get("FARM_TWIN_WORKER_FACTORY")
    if not target or ":" not in target:
        raise RuntimeError("FARM_TWIN_WORKER_FACTORY must be set to module:callable")
    module_name, attribute = target.split(":", 1)
    session_factory, handlers = getattr(importlib.import_module(module_name), attribute)()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await run_worker(session_factory, handlers, stop)


if __name__ == "__main__":
    asyncio.run(serve())
