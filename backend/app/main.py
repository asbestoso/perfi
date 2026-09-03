"""FastAPI entrypoint: CORS + /api router + lifespan init_db+seed."""
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from . import logging_setup
from .config import settings
from .database import init_db
from .api.routes.api import router

log = logging_setup.get("http")


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        started = time.perf_counter()
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            log.exception(f"{request.method} {request.url.path} -> 500")
            raise
        ms = (time.perf_counter() - started) * 1000
        log.info(f"{request.method} {request.url.path} -> {status} ({ms:.0f}ms)")
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logging_setup.setup()  # re-assert after Alembic's fileConfig
    log.info("perfi boot complete")
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(RequestLogMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router, prefix="/api")


@app.exception_handler(Exception)
async def _unhandled(request, exc):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
