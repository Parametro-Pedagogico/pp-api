"""Administração de grupos e módulos de navegação."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.domains.navigation import admin_service as svc
from app.domains.navigation import repository as repo
from app.v1._scope import is_admin_like
from app.v1.navigation_schemas import (
    AccessMatrixEntryV1,
    AccessMatrixModuleOutV1,
    AccessMatrixOutV1,
    AccessMatrixRoleOutV1,
    AccessMatrixUpdateV1,
    NavigationGroupAdminOutV1,
    NavigationGroupCreateV1,
    NavigationGroupUpdateV1,
    NavigationModuleAdminOutV1,
    NavigationModuleCreateV1,
    NavigationModuleUpdateV1,
)

router = APIRouter(prefix="/admin/navigation", tags=["v1-navigation-admin"])


def _assert_platform_admin(ctx: AuthContext) -> None:
    if not is_admin_like(ctx.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas administradores da plataforma")


def _serialize_group(row: dict) -> NavigationGroupAdminOutV1:
    return NavigationGroupAdminOutV1(
        id=UUID(str(row["id"])),
        code=str(row["code"]),
        name=str(row["name"]),
        description=row.get("description"),
        icon_key=row.get("icon_key"),
        sort_order=int(row["sort_order"]),
        is_active=bool(row["is_active"]),
        module_count=int(row.get("module_count") or 0),
    )


def _serialize_module(row: dict) -> NavigationModuleAdminOutV1:
    return NavigationModuleAdminOutV1(
        id=UUID(str(row["id"])),
        group_id=UUID(str(row["group_id"])),
        group_code=row.get("group_code"),
        group_name=row.get("group_name"),
        code=str(row["code"]),
        name=str(row["name"]),
        description=row.get("description"),
        route_path=str(row["route_path"]),
        icon_key=row.get("icon_key"),
        sort_order=int(row["sort_order"]),
        is_active=bool(row["is_active"]),
        match_prefix=bool(row.get("match_prefix", True)),
        required_feature_flag=row.get("required_feature_flag"),
    )


@router.get("/groups", response_model=list[NavigationGroupAdminOutV1])
async def list_navigation_groups_admin(
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    rows = await svc.list_groups_admin(db)
    return [_serialize_group(r) for r in rows]


@router.post("/groups", response_model=NavigationGroupAdminOutV1, status_code=status.HTTP_201_CREATED)
async def create_navigation_group_admin(
    body: NavigationGroupCreateV1,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    row = await svc.create_group(db, body, ctx)
    return _serialize_group(row)


@router.patch("/groups/{group_id}", response_model=NavigationGroupAdminOutV1)
async def update_navigation_group_admin(
    group_id: UUID,
    body: NavigationGroupUpdateV1,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    row = await svc.update_group(db, group_id, body, ctx)
    return _serialize_group(row)


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_navigation_group_admin(
    group_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    await svc.delete_group(db, group_id, ctx)


@router.get("/modules", response_model=list[NavigationModuleAdminOutV1])
async def list_navigation_modules_admin(
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    group_id: UUID | None = Query(default=None),
):
    _assert_platform_admin(ctx)
    rows = await svc.list_modules_admin(db, group_id=group_id)
    return [_serialize_module(r) for r in rows]


@router.post("/modules", response_model=NavigationModuleAdminOutV1, status_code=status.HTTP_201_CREATED)
async def create_navigation_module_admin(
    body: NavigationModuleCreateV1,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    row = await svc.create_module(db, body, ctx)
    return _serialize_module(row)


@router.patch("/modules/{module_id}", response_model=NavigationModuleAdminOutV1)
async def update_navigation_module_admin(
    module_id: UUID,
    body: NavigationModuleUpdateV1,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    row = await svc.update_module(db, module_id, body, ctx)
    return _serialize_module(row)


@router.delete("/modules/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_navigation_module_admin(
    module_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    await svc.delete_module(db, module_id, ctx)


@router.get("/icon-keys", response_model=list[str])
async def list_navigation_icon_keys(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    from app.v1.navigation_schemas import ALLOWED_ICON_KEYS

    return sorted(ALLOWED_ICON_KEYS)


def _serialize_access_matrix(data: dict) -> AccessMatrixOutV1:
    return AccessMatrixOutV1(
        roles=[
            AccessMatrixRoleOutV1(
                id=UUID(str(r["id"])),
                code=str(r["code"]),
                name=str(r["name"]),
                sort_order=int(r["sort_order"]),
                is_active=bool(r.get("is_active", True)),
            )
            for r in data.get("roles") or []
        ],
        modules=[
            AccessMatrixModuleOutV1(
                id=UUID(str(m["id"])),
                code=str(m["code"]),
                name=str(m["name"]),
                group_id=UUID(str(m["group_id"])),
                group_code=str(m["group_code"]),
                group_name=str(m["group_name"]),
                group_sort_order=int(m["group_sort_order"]),
                sort_order=int(m["sort_order"]),
                is_active=bool(m.get("is_active", True)),
            )
            for m in data.get("modules") or []
        ],
        access=[
            AccessMatrixEntryV1(
                role_definition_id=UUID(str(a["role_definition_id"])),
                navigation_module_id=UUID(str(a["navigation_module_id"])),
                access_level=a["access_level"],  # type: ignore[arg-type]
            )
            for a in data.get("access") or []
        ],
    )


@router.get("/access-matrix", response_model=AccessMatrixOutV1)
async def get_access_matrix_admin(
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    data = await svc.get_access_matrix(db)
    return _serialize_access_matrix(data)


@router.put("/access-matrix", response_model=AccessMatrixOutV1)
async def update_access_matrix_admin(
    body: AccessMatrixUpdateV1,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    updates = [u.model_dump() for u in body.updates]
    data = await svc.update_access_matrix(db, updates, ctx)
    return _serialize_access_matrix(data)
