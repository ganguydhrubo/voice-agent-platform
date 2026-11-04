"""The FastAPI application: API, voice socket, metrics and the built web app."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from backend.api import admin, auth, public
from backend.config import Settings, get_settings
from backend.db import now_iso
from backend.retention import retention_loop
from backend.runtime import Runtime
from backend.security import SecurityMiddleware, came_through_proxy, client_ip
from backend.seed import seed

log = logging.getLogger("vap.main")
DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"


def friendly_error(error: RequestValidationError) -> str:
    first = error.errors()[0]
    message = first.get("msg", "This value is not valid").removeprefix("Value error, ")
    return message if message.endswith(".") else f"{message}."


def create_app(settings: Settings | None = None, *, light: bool = False, runtime: Runtime | None = None) -> FastAPI:
    settings = settings or get_settings()
    runtime = runtime or Runtime(settings, light=light)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await asyncio.to_thread(seed, runtime)
        await runtime.start()
        task = asyncio.create_task(retention_loop(runtime))
        log.info("Ready. Open %s", settings.public_origin)
        yield
        task.cancel()
        await runtime.stop()

    public_docs = not settings.is_production
    app = FastAPI(
        title="Voice Agent Platform",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs" if public_docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if public_docs else None,
    )
    app.state.runtime = runtime
    app.add_middleware(
        SecurityMiddleware,
        limiter=runtime.api_limiter,
        public_origin=settings.public_origin,
        production=settings.is_production,
    )
    app.include_router(auth.router)
    app.include_router(public.router)
    app.include_router(admin.router)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse({"detail": friendly_error(error)}, status_code=422)

    @app.get("/metrics", include_in_schema=False)
    def prometheus(request: Request) -> PlainTextResponse:
        local = client_ip(request) in ("127.0.0.1", "::1", "testclient") and not came_through_proxy(request)
        if not local and not settings.metrics_open:
            raise HTTPException(404, "Not found.")
        runtime.sessions.snapshot()
        return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    if DIST.exists():
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def web_app(path: str) -> FileResponse:
            if path.startswith(("api/", "ws/")):
                raise HTTPException(404, "Not found.")
            candidate = (DIST / path).resolve()
            if path and candidate.is_file() and DIST.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-cache"})

    log.debug("Application built at %s", now_iso())
    return app


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, ws_max_size=1 << 20, log_level="info", access_log=False)


if __name__ == "__main__":
    main()
