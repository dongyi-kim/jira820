"""make_app: assemble the FastAPI application from the read/write/agile routers."""

from __future__ import annotations

import asyncio

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import server_agile, server_attach, server_read, server_write
from .config import Config, load_config
from .store import JiraError, Store


def build_store(config: Config = None) -> Store:
    return Store(config or load_config())


def make_app(store: Store = None, config: Config = None) -> FastAPI:
    """Build the app. Pass a `store` to inject your own data source; otherwise one is seeded."""
    if store is None:
        store = build_store(config)
    app = FastAPI(title=f"Jira DC {store.config.server_version} mock", version="0.2.0")
    app.state.store = store

    @app.middleware("http")
    async def _latency(request: Request, call_next):
        ms = store.config.latency_ms
        if ms:
            await asyncio.sleep(ms / 1000.0)
        return await call_next(request)

    @app.exception_handler(JiraError)
    async def _jira_error(request: Request, exc: JiraError):
        return JSONResponse(exc.body(), status_code=exc.status_code)

    app.include_router(server_read.router)
    app.include_router(server_write.router)
    app.include_router(server_agile.router)
    app.include_router(server_attach.router)
    return app
