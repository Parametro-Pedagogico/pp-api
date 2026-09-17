"""Status page pública — componentes cadastrados no admin."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.v1 import status_page_store as store

router = APIRouter(tags=["Health"])

OverallStatus = Literal["operational", "degraded", "major_outage"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _overall(components: list[dict[str, Any]]) -> OverallStatus:
    statuses = {c.get("status") for c in components}
    if "major_outage" in statuses:
        return "major_outage"
    if "degraded" in statuses or "unknown" in statuses:
        return "degraded"
    return "operational"


@router.get("/status")
async def platform_status_v1(
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    components = await store.list_public_status(db)
    for comp in components:
        comp.pop("component_id", None)

    status = _overall(components)
    if status == "major_outage":
        response.status_code = 503

    return {
        "status": status,
        "service": "parametro-pedagogico-api",
        "checked_at": _now_iso(),
        "components": components,
        "summary": {
            "operational": sum(1 for c in components if c["status"] == "operational"),
            "degraded": sum(1 for c in components if c["status"] == "degraded"),
            "major_outage": sum(1 for c in components if c["status"] == "major_outage"),
            "total": len(components),
        },
    }
