"""Portable project discovery; membership is the sole project visibility boundary."""

from fastapi import APIRouter, Query, Response
from starlette.concurrency import run_in_threadpool

from ..config import settings
from ..media.store import MediaStore
from .media_library import User, authorize

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.get("/projects")
async def projects(principal: User, response: Response, offset: int = Query(0, ge=0)) -> dict:
    response.headers["Cache-Control"] = "private, no-store"

    def read():
        with MediaStore(settings.database_url).connection() as conn:
            return conn.execute(
                "SELECT p.id,p.name,m.role FROM projects p JOIN project_members m "
                "ON m.project_id=p.id WHERE m.email=%s ORDER BY p.id LIMIT 50 OFFSET %s",
                (principal.email, offset),
            ).fetchall()

    return {"projects": await run_in_threadpool(read)}


@router.get("/{project}/summary")
async def summary(project: int, principal: User, response: Response) -> dict:
    await authorize(principal, project, "read")
    response.headers["Cache-Control"] = "private, no-store"

    def read():
        with MediaStore(settings.database_url).connection() as conn:
            sources = conn.execute(
                "SELECT count(*) AS total FROM media_sources WHERE project_id=%s", (project,)
            ).fetchone()["total"]
            timelines = conn.execute(
                "SELECT document_id,revision FROM state_documents "
                "WHERE project_id=%s AND kind='canonical_timeline' ORDER BY document_id LIMIT 100",
                (project,),
            ).fetchall()
            jobs = conn.execute(
                "SELECT kind,state,count(*) AS count FROM jobs WHERE project_id=%s "
                "GROUP BY kind,state ORDER BY kind,state",
                (project,),
            ).fetchall()
        return {
            "sources": sources,
            "timelines": timelines,
            "jobs": jobs,
            "inference_mode": settings.inference_mode,
            "quality_acceptance": "pending",
        }

    return await run_in_threadpool(read)
