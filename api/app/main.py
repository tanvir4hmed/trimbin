"""Trimbin API.

Two audiences, one service. Members work on their projects; anyone at all can
read the demo project and the accuracy pages without an account, because a
system that publishes its own error rate should not put that behind a signup.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .routes import projects, public, review, uploads
from .services import analytics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
)
log = logging.getLogger("trimbin")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("starting, project=%s region=%s", settings.project_id, settings.region)
    yield
    # Cloud Run stops instances routinely; leaving connections open leaks them
    # a few at a time until the database refuses new ones.
    await analytics.close()
    log.info("stopped")


app = FastAPI(
    title="Trimbin",
    description="An assistant editor that never forgets.",
    version="0.1.0",
    lifespan=lifespan,
)

# Named origins only. A wildcard would let any page in a viewer's browser call
# this with their session attached.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://trimbin.qlitch.com",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(public.router)
app.include_router(uploads.router)
app.include_router(review.router)
app.include_router(projects.router)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    """Log the detail, return a sentence.

    An internal error message in a response tells an attacker about the schema
    and tells a user nothing they can act on. The log has what is needed to fix
    it; the response has what is needed to move on.
    """
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong on our side. Please try again."},
    )


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "trimbin",
        "docs": "/docs",
        "accuracy": "/public/accuracy",
    }
