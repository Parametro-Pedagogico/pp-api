"""CRUD administrativo de papéis (role_definitions)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext
from app.domains.navigation.repository import insert_navigation_audit
from app.domains.rbac import role_repository as repo
from app.v1.navigation_schemas import RoleDefinitionCreateV1, RoleDefinitionUpdateV1

CORE_ROLE_CODES = frozenset({"student", "teacher", "school_admin", "platform_admin"})


async def list_roles_admin(
    db: AsyncSession,
    *,
    is_active: bool | None = None,
    assignable_only: bool = False,
) -> list[dict[str, Any]]:
    return await repo.list_role_definitions_with_aliases(
        db,
        is_active=is_active,
        assignable_only=assignable_only,
    )


async def get_role_admin(db: AsyncSession, role_id: UUID) -> dict[str, Any]:
    rows = await repo.list_role_definitions_with_aliases(db)
    row = next((r for r in rows if str(r["id"]) == str(role_id)), None)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Papel não encontrado")
    return row


async def create_role(
    db: AsyncSession,
    body: RoleDefinitionCreateV1,
    ctx: AuthContext,
) -> dict[str, Any]:
    if await repo.get_role_definition_by_code(db, body.code):
        raise HTTPException(status.HTTP_409_CONFLICT, "Código de papel já existe")
    sort_order = body.sort_order if body.sort_order is not None else await repo.max_role_sort_order(db) + 10
    row = await repo.insert_role_definition(
        db,
        code=body.code,
        name=body.name,
        description=body.description,
        scope_type=body.scope_type,
        sort_order=sort_order,
        is_active=body.is_active,
    )
    await insert_navigation_audit(
        db,
        entity_type="role_definition",
        entity_id=UUID(str(row["id"])),
        action="create",
        actor_profile_id=ctx.active_profile_id,
        actor_person_id=ctx.person_id,
        previous_values=None,
        new_values={"code": body.code, "name": body.name},
    )
    await db.commit()
    row["aliases"] = []
    return row


async def update_role(
    db: AsyncSession,
    role_id: UUID,
    body: RoleDefinitionUpdateV1,
    ctx: AuthContext,
) -> dict[str, Any]:
    before = await repo.get_role_definition(db, role_id)
    if not before:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Papel não encontrado")

    if body.is_active is False:
        code = str(before["code"])
        if code in CORE_ROLE_CODES:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"O papel base {code} não pode ser inativado.",
            )

    if body.scope_type is not None and body.scope_type != str(before["scope_type"]):
        if bool(before["is_system"]):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Escopo de papéis do sistema não pode ser alterado.",
            )

    row = await repo.update_role_definition(
        db,
        role_id,
        name=body.name,
        description=body.description,
        scope_type=body.scope_type,
        sort_order=body.sort_order,
        is_active=body.is_active,
    )
    assert row is not None
    await insert_navigation_audit(
        db,
        entity_type="role_definition",
        entity_id=role_id,
        action="update",
        actor_profile_id=ctx.active_profile_id,
        actor_person_id=ctx.person_id,
        previous_values={"name": before["name"], "is_active": before["is_active"]},
        new_values={"name": row["name"], "is_active": row["is_active"]},
    )
    await db.commit()
    return await get_role_admin(db, role_id)


async def delete_role(
    db: AsyncSession,
    role_id: UUID,
    ctx: AuthContext,
) -> None:
    before = await repo.get_role_definition(db, role_id)
    if not before:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Papel não encontrado")

    code = str(before["code"])
    if code in CORE_ROLE_CODES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"O papel base {code} não pode ser excluído.",
        )
    if bool(before["is_active"]):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Inative o perfil antes de excluí-lo.",
        )

    linked_profiles = await repo.count_profiles_linked_to_role(db, role_id, code)
    if linked_profiles > 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Este perfil ainda está vinculado a {linked_profiles} usuário(s). "
            "Reatribua ou remova esses perfis antes de excluir.",
        )

    await repo.delete_role_definition(db, role_id)
    await insert_navigation_audit(
        db,
        entity_type="role_definition",
        entity_id=role_id,
        action="delete",
        actor_profile_id=ctx.active_profile_id,
        actor_person_id=ctx.person_id,
        previous_values={"code": before["code"], "name": before["name"]},
        new_values=None,
    )
    await db.commit()
