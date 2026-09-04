"""Enforcement de acesso por módulo (matriz role_module_access)."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext
from app.domains.rbac import role_repository as role_repo
from app.v1._scope import is_admin_like
from app.v1._sql import fetch_one

ACCESS_RANK: dict[str, int] = {
    "NONE": 0,
    "VIEW": 1,
    "EDIT": 2,
    "MANAGE": 3,
}

AccessLevel = str


async def resolve_role_definition_id_for_context(
    db: AsyncSession,
    ctx: AuthContext,
) -> UUID | None:
    row = await role_repo.resolve_role_definition(db, ctx.role)
    if row:
        return UUID(str(row["id"]))
    profile = await fetch_one(
        db,
        """
        SELECT role_definition_id
        FROM profiles
        WHERE id = CAST(:id AS uuid)
        """,
        {"id": str(ctx.active_profile_id)},
    )
    if profile and profile.get("role_definition_id"):
        return UUID(str(profile["role_definition_id"]))
    return None


async def get_module_access_level(
    db: AsyncSession,
    ctx: AuthContext,
    module_code: str,
) -> AccessLevel:
    if is_admin_like(ctx.role):
        return "MANAGE"
    role_id = await resolve_role_definition_id_for_context(db, ctx)
    if not role_id:
        return "NONE"
    row = await fetch_one(
        db,
        """
        SELECT rma.access_level
        FROM role_module_access rma
        JOIN navigation_modules m ON m.id = rma.navigation_module_id
        WHERE rma.role_definition_id = CAST(:role_id AS uuid)
          AND m.code = :module_code
          AND rma.is_active = true
          AND m.is_active = true
        """,
        {"role_id": str(role_id), "module_code": module_code},
    )
    if not row:
        return "NONE"
    return str(row["access_level"])


async def assert_module_access(
    db: AsyncSession,
    ctx: AuthContext,
    module_code: str,
    min_level: AccessLevel,
) -> None:
    level = await get_module_access_level(db, ctx, module_code)
    required = ACCESS_RANK.get(min_level.upper(), 0)
    current = ACCESS_RANK.get(level.upper(), 0)
    if current < required:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Sem permissão suficiente para o módulo «{module_code}»",
        )
