"""Catálogo administrável de papéis (role definitions)."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.domains.rbac import role_admin_service as svc
from app.v1._scope import is_admin_like, is_staff_admin_role
from app.v1.navigation_schemas import (
    RoleDefinitionCreateV1,
    RoleDefinitionOutV1,
    RoleDefinitionUpdateV1,
)

router = APIRouter(prefix="/admin/role-definitions", tags=["v1-role-definitions-admin"])


def _serialize(row: dict[str, Any]) -> RoleDefinitionOutV1:
    aliases_raw = row.get("aliases") or []
    aliases = [str(a) for a in aliases_raw] if isinstance(aliases_raw, list) else []
    return RoleDefinitionOutV1(
        id=UUID(str(row["id"])),
        code=str(row["code"]),
        name=str(row["name"]),
        description=row.get("description"),
        scope_type=str(row["scope_type"]),
        is_system=bool(row["is_system"]),
        is_active=bool(row["is_active"]),
        sort_order=int(row["sort_order"]),
        aliases=aliases,
    )


def _assert_platform_admin(ctx: AuthContext) -> None:
    if not is_admin_like(ctx.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas administradores da plataforma")


def _assert_can_list(ctx: AuthContext, *, assignable: bool) -> None:
    if assignable:
        if not is_staff_admin_role(ctx.role):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão")
        return
    _assert_platform_admin(ctx)


@router.get("", response_model=list[RoleDefinitionOutV1])
async def list_role_definitions(
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    is_active: bool | None = Query(default=None),
):
    _assert_can_list(ctx, assignable=False)
    rows = await svc.list_roles_admin(db, is_active=is_active)
    return [_serialize(r) for r in rows]


@router.get("/assignable", response_model=list[RoleDefinitionOutV1])
async def list_assignable_role_definitions(
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_can_list(ctx, assignable=True)
    rows = await svc.list_roles_admin(db, assignable_only=True)
    return [_serialize(r) for r in rows]


@router.get("/{role_id}", response_model=RoleDefinitionOutV1)
async def get_role_definition_admin(
    role_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    row = await svc.get_role_admin(db, role_id)
    return _serialize(row)


@router.post("", response_model=RoleDefinitionOutV1, status_code=status.HTTP_201_CREATED)
async def create_role_definition_admin(
    body: RoleDefinitionCreateV1,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    row = await svc.create_role(db, body, ctx)
    return _serialize(row)


@router.patch("/{role_id}", response_model=RoleDefinitionOutV1)
async def update_role_definition_admin(
    role_id: UUID,
    body: RoleDefinitionUpdateV1,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    row = await svc.update_role(db, role_id, body, ctx)
    return _serialize(row)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role_definition_admin(
    role_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    await svc.delete_role(db, role_id, ctx)
