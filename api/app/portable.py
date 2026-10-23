"""Portable API entrypoint. Legacy endpoints are not mounted on this application."""

from fastapi import FastAPI

from .main import evidence_error, inference_error, media_error
from .routes import (
    editable_exports,
    evidence,
    inference,
    media_library,
    renders,
    session,
    timelines,
    workflow,
)

app = FastAPI(title="Trimbin portable workflow", version="0.1.0")
for router in (
    session.router,
    workflow.router,
    media_library.router,
    inference.router,
    evidence.router,
    timelines.router,
    editable_exports.router,
    renders.router,
):
    app.include_router(router)
app.add_exception_handler(evidence.EvidenceError, evidence_error)
app.add_exception_handler(evidence.InferenceError, inference_error)
app.add_exception_handler(media_library.MediaError, media_error)


@app.get("/health")
def health():
    # Liveness only: does not pretend providers, workers or quality gates are ready.
    return {"status": "alive", "runtime": "portable"}
