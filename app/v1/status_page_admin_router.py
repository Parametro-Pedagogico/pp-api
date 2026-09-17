"""CRUD admin dos componentes da status page."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.v1._scope import is_admin_like
from app.v1 import status_page_store as store

router = APIRouter(prefix="/admin/status-components", tags=["v1-status-page-admin"])


def _assert_platform_admin(ctx: AuthContext) -> None:
    if not is_admin_like(ctx.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas administradores da plataforma")


CheckModeLiteral = Literal["manual", "probe_database", "probe_firebase_admin"]
StatusLiteral = Literal["operational", "degraded", "major_outage"]


class StatusComponentOutV1(BaseModel):
    id: UUID
    slug: str
    name: str
    description: str | None = None
    sort_order: int
    check_mode: CheckModeLiteral
    manual_status: StatusLiteral
    is_visible: bool


class StatusComponentCreateV1(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    sort_order: int = 0
    check_mode: CheckModeLiteral = "manual"
    manual_status: StatusLiteral = "operational"
    is_visible: bool = True


class StatusComponentUpdateV1(BaseModel):
    slug: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    sort_order: int | None = None
    check_mode: CheckModeLiteral | None = None
    manual_status: StatusLiteral | None = None
    is_visible: bool | None = None


def _serialize(row: dict[str, Any]) -> StatusComponentOutV1:
    return StatusComponentOutV1(
        id=UUID(str(row["id"])),
        slug=str(row["slug"]),
        name=str(row["name"]),
        description=row.get("description"),
        sort_order=int(row.get("sort_order") or 0),
        check_mode=str(row.get("check_mode") or "manual"),  # type: ignore[arg-type]
        manual_status=str(row.get("manual_status") or "operational"),  # type: ignore[arg-type]
        is_visible=bool(row.get("is_visible", True)),
    )


@router.get("", response_model=list[StatusComponentOutV1])
async def list_status_components_admin(
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    rows = await store.list_admin_components(db)
    return [_serialize(r) for r in rows]


@router.post("", response_model=StatusComponentOutV1, status_code=status.HTTP_201_CREATED)
async def create_status_component_admin(
    body: StatusComponentCreateV1,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    try:
        row = await store.create_admin_component(db, body.model_dump())
        await db.commit()
    except Exception as exc:
        await db.rollback()
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise HTTPException(status.HTTP_409_CONFLICT, "Slug já existe") from exc
        raise
    return _serialize(row)


@router.patch("/{component_id}", response_model=StatusComponentOutV1)
async def update_status_component_admin(
    component_id: UUID,
    body: StatusComponentUpdateV1,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    payload = body.model_dump(exclude_unset=True)
    try:
        row = await store.update_admin_component(db, component_id, payload)
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Componente não encontrado")
        await db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        if "unique" in str(exc).lower():
            raise HTTPException(status.HTTP_409_CONFLICT, "Slug já existe") from exc
        raise
    return _serialize(row)


@router.delete("/{component_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_status_component_admin(
    component_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    ok = await store.delete_admin_component(db, component_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Componente não encontrado")
    await db.commit()
