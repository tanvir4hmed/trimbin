"""Public configuration status only. Live evaluation is operator-only until Phase 5."""

from fastapi import APIRouter
from trimbin_agents.config import placeholder

from ..config import settings
from ..inference.provider import InferenceError, live_preflight, load_catalog

router = APIRouter(prefix="/inference", tags=["inference"])


@router.get("/status")
def status() -> dict:
    report = {
        "mode": settings.inference_mode,
        "live_enabled": settings.inference_live_enabled,
        "live_verified": False,
        "quality_status": "not_evaluated",
        "speech": "adapter_unavailable",
        "editorial_integration": "pending",
        "status": "unavailable",
    }
    if settings.inference_mode == "fixture":
        report["status"] = "explicit_fixture_only"
        return report
    try:
        live_preflight(settings)
        catalog = load_catalog(settings.inference_catalog_path)
        if not any(
            model in catalog and not placeholder(model)
            for model in (settings.reasoning_model, settings.vision_model)
        ):
            raise InferenceError("model_profile_missing")
        report["status"] = "configured_unverified"
    except InferenceError as exc:
        report["reason"] = exc.code
    return report
