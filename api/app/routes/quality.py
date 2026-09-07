"""Project-scoped live quality statistics, including anonymous public access."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from ..auth import Principal, current_principal
from ..services import quality

router = APIRouter(prefix="/quality", tags=["quality"])


@router.get("", response_model=quality.QualityReport)
async def report(
    response: Response,
    principal: Annotated[Principal, Depends(current_principal)],
) -> quality.QualityReport:
    response.headers["Cache-Control"] = "private, no-store"
    return await quality.report(principal.email or "")
