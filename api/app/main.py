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
from .routes import (
    ask,
    dashboard,
    maintenance,
    projects,
    public,
    review,
    scenes,
    uploads,
)
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
    # PUT is here because the brief, the circled take, the assignee and the set
    # state are all replacements of one field rather than events, and a POST for
    # each would make four ways to say the same thing. It was missing when those
    # routes were added, and the failure would have been a CORS preflight
    # rejection in the browser with a working endpoint behind it.
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(public.router)
app.include_router(dashboard.router)
app.include_router(uploads.router)
app.include_router(review.router)
app.include_router(scenes.router)
app.include_router(projects.router)
app.include_router(maintenance.router)
app.include_router(ask.router)


@app.exception_handler(analytics.Waking)
async def waking(request: Request, exc: analytics.Waking) -> JSONResponse:
    """A cold database is a wait, not a fault.

    503 with Retry-After rather than 500, so the difference reaches the client
    as something it can act on. The interface then says "this can take a
    moment" instead of "something went wrong" — which matters because the
    person who sees this most often is the one who arrived first, and telling
    them the system is broken when it is merely asleep is how a working demo
    reads as a broken one.
    """
    log.info("archive still waking on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=503,
        headers={"Retry-After": "20"},
        content={
            "detail": (
                "The archive is waking up — it sleeps when nobody is using it. "
                "This takes about half a minute."
            ),
            "waking": True,
        },
    )


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
