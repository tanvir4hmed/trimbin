"""The worker's front door.

Pub/Sub delivers by HTTP POST, so the worker is a web service that happens to
spend its time in ffmpeg. That shape is deliberate: it scales to zero between
shoots and to many instances during one, and a pull loop would do neither — it
would idle at a cost all night to be ready for a morning that may not come.

Nothing here verifies the caller. Cloud Run does it, because the service is
deployed without an allUsers binding and only the push subscription's service
account holds run.invoker. Checking the token again in Python would be a second
implementation of the same rule, and two implementations of one rule eventually
disagree.

The reply is the acknowledgement:

    204   done with it, never send it again
    500   we failed, send it back

There is no third answer. A clip we cannot use is a 204 with a recorded reason,
because redelivering a corrupt file four more times produces the same verdict
four more times.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status

from ..config import settings
from ..services import analytics
from .ingest import handle_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
)
log = logging.getLogger("trimbin.worker")

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("ingest worker ready, project=%s", settings.project_id)
    yield
    # Cloud Run stops idle instances constantly, and each one holding a
    # ClickHouse connection open on the way out leaks them until the database
    # starts refusing new ones.
    await analytics.close()


app = FastAPI(
    title="Trimbin ingest worker",
    description="Measures a clip, builds its proxy, records what it found.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Startup probe only. It touches nothing, so it answers while ffmpeg runs."""
    return {"status": "ok", "role": "ingest-worker", "project": settings.project_id}


def _attributes(envelope: dict) -> dict[str, str]:
    """Pull the clip's identity out of a push envelope.

    The publisher puts everything in attributes, and the data field carries a
    copy for anyone reading the topic by hand. Attributes win: they are what the
    publisher is contracted to set, and preferring the body would let a
    malformed copy override a correct header.
    """
    message = envelope.get("message") or {}
    attributes = dict(message.get("attributes") or {})
    if attributes:
        return attributes

    raw = message.get("data")
    if not raw:
        return {}
    try:
        return json.loads(base64.b64decode(raw))
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return {}


@app.post("/pubsub")
async def receive(request: Request) -> Response:
    try:
        envelope = await request.json()
    except ValueError:
        # Unparseable. Retrying cannot make it parse, so it is acknowledged and
        # logged rather than left to cycle through the retry policy.
        log.warning("discarding a push with a body that is not JSON")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    attributes = _attributes(envelope)
    if not {"job_id", "clip_id"} <= attributes.keys():
        log.warning("discarding a push with no clip in it: %s", sorted(attributes))
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    delivery = (envelope.get("deliveryAttempt") or 1)
    log.info("clip %s, attempt %s", attributes["clip_id"], delivery)

    try:
        acknowledge = await handle_message(attributes)
    except (KeyError, ValueError) as exc:
        # Malformed identifiers, not a processing failure. handle_message parses
        # them before its own try block, so this is the only place they surface.
        log.warning("discarding a push we cannot address: %s", exc)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    if acknowledge:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return Response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content="processing failed, please redeliver",
        media_type="text/plain",
    )
