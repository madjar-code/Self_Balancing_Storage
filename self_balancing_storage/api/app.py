from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..runtime import Runtime
from ..query.parser import QueryParseError
from . import routes_logs, routes_query, routes_admin, routes_events


def create_app(runtime: Runtime) -> FastAPI:
    app = FastAPI(title="Self-Balancing Storage", version="2.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _get_runtime() -> Runtime:
        return runtime

    app.dependency_overrides[routes_logs.get_runtime] = _get_runtime
    app.dependency_overrides[routes_query.get_runtime] = _get_runtime
    app.dependency_overrides[routes_admin.get_runtime] = _get_runtime
    app.dependency_overrides[routes_events.get_runtime] = _get_runtime

    app.include_router(routes_logs.router)
    app.include_router(routes_query.router)
    app.include_router(routes_admin.router)
    app.include_router(routes_events.router)

    @app.exception_handler(QueryParseError)
    async def query_parse_handler(request, exc):
        return JSONResponse(
            status_code=400,
            content={
                "error": "query_parse_error",
                "detail": exc.pretty(),
                "position": exc.position,
            },
        )

    return app
