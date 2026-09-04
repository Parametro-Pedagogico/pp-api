"""CRUD administrativo de grupos e módulos de navegação."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext
from app.domains.navigation import repository as repo
from app.v1.navigation_schemas import (
    NavigationGroupCreateV1,
    NavigationGroupUpdateV1,
    NavigationModuleCreateV1,
    NavigationModuleUpdateV1,
)


async def list_groups_admin(db: AsyncSession) -> list[dict[str, Any]]:
    return await repo.list_navigation_groups(db, include_inactive=True)


async def list_modules_admin(
    db: AsyncSession,
    *,
    group_id: UUID | None = None,
) -> list[dict[str, Any]]:
    return await repo.list_navigation_modules(db, group_id=group_id, include_inactive=True)


async def create_group(
    db: AsyncSession,
    body: NavigationGroupCreateV1,
    ctx: AuthContext,
) -> dict[str, Any]:
    if await repo.get_navigation_group_by_code(db, body.code):
        raise HTTPException(status.HTTP_409_CONFLICT, "Código de grupo já existe")
    sort_order = body.sort_order if body.sort_order is not None else await repo.max_group_sort_order(db) + 10
    row = await repo.insert_navigation_group(
        db,
        code=body.code,
        name=body.name,
        description=body.description,
        icon_key=body.icon_key,
        sort_order=sort_order,
        is_active=body.is_active,
    )
    await repo.insert_navigation_audit(
        db,
        entity_type="navigation_group",
        entity_id=UUID(str(row["id"])),
        action="create",
        actor_profile_id=ctx.active_profile_id,
        actor_person_id=ctx.person_id,
        previous_values=None,
        new_values={"code": body.code, "name": body.name},
    )
    await db.commit()
    row["module_count"] = 0
    return row


async def update_group(
    db: AsyncSession,
    group_id: UUID,
    body: NavigationGroupUpdateV1,
    ctx: AuthContext,
) -> dict[str, Any]:
    before = await repo.get_navigation_group(db, group_id)
    if not before:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grupo não encontrado")
    row = await repo.update_navigation_group(
        db,
        group_id,
        name=body.name,
        description=body.description,
        icon_key=body.icon_key,
        sort_order=body.sort_order,
        is_active=body.is_active,
    )
    assert row is not None
    await repo.insert_navigation_audit(
        db,
        entity_type="navigation_group",
        entity_id=group_id,
        action="update",
        actor_profile_id=ctx.active_profile_id,
        actor_person_id=ctx.person_id,
        previous_values={"name": before["name"], "is_active": before["is_active"]},
        new_values={"name": row["name"], "is_active": row["is_active"]},
    )
    await db.commit()
    groups = await repo.list_navigation_groups(db, include_inactive=True)
    enriched = next((g for g in groups if str(g["id"]) == str(group_id)), row)
    return enriched


async def delete_group(
    db: AsyncSession,
    group_id: UUID,
    ctx: AuthContext,
) -> None:
    before = await repo.get_navigation_group(db, group_id)
    if not before:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grupo não encontrado")
    module_count = await repo.count_modules_in_group(db, group_id)
    if module_count > 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Não é possível excluir um grupo que ainda possui módulos.",
        )
    await repo.delete_navigation_group(db, group_id)
    await repo.insert_navigation_audit(
        db,
        entity_type="navigation_group",
        entity_id=group_id,
        action="delete",
        actor_profile_id=ctx.active_profile_id,
        actor_person_id=ctx.person_id,
        previous_values={"code": before["code"], "name": before["name"]},
        new_values=None,
    )
    await db.commit()


async def create_module(
    db: AsyncSession,
    body: NavigationModuleCreateV1,
    ctx: AuthContext,
) -> dict[str, Any]:
    group = await repo.get_navigation_group(db, body.group_id)
    if not group:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Grupo inválido")
    existing = await repo.list_navigation_modules(db, include_inactive=True)
    if any(str(m["code"]) == body.code for m in existing):
        raise HTTPException(status.HTTP_409_CONFLICT, "Código de módulo já existe")
    sort_order = (
        body.sort_order
        if body.sort_order is not None
        else await repo.max_module_sort_order(db, body.group_id) + 10
    )
    row = await repo.insert_navigation_module(
        db,
        group_id=body.group_id,
        code=body.code,
        name=body.name,
        description=body.description,
        route_path=body.route_path,
        icon_key=body.icon_key,
        sort_order=sort_order,
        is_active=body.is_active,
        match_prefix=body.match_prefix,
        required_feature_flag=body.required_feature_flag,
    )
    await repo.insert_navigation_audit(
        db,
        entity_type="navigation_module",
        entity_id=UUID(str(row["id"])),
        action="create",
        actor_profile_id=ctx.active_profile_id,
        actor_person_id=ctx.person_id,
        previous_values=None,
        new_values={"code": body.code, "route_path": body.route_path},
    )
    await db.commit()
    full = await repo.get_navigation_module(db, UUID(str(row["id"])))
    assert full is not None
    return full


async def update_module(
    db: AsyncSession,
    module_id: UUID,
    body: NavigationModuleUpdateV1,
    ctx: AuthContext,
) -> dict[str, Any]:
    before = await repo.get_navigation_module(db, module_id)
    if not before:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Módulo não encontrado")
    if body.group_id is not None:
        group = await repo.get_navigation_group(db, body.group_id)
        if not group:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Grupo inválido")
    row = await repo.update_navigation_module(
        db,
        module_id,
        group_id=body.group_id,
        name=body.name,
        description=body.description,
        route_path=body.route_path,
        icon_key=body.icon_key,
        sort_order=body.sort_order,
        is_active=body.is_active,
        match_prefix=body.match_prefix,
        required_feature_flag=body.required_feature_flag,
    )
    assert row is not None
    await repo.insert_navigation_audit(
        db,
        entity_type="navigation_module",
        entity_id=module_id,
        action="update",
        actor_profile_id=ctx.active_profile_id,
        actor_person_id=ctx.person_id,
        previous_values={"name": before["name"], "is_active": before["is_active"]},
        new_values={"name": row["name"], "is_active": row["is_active"]},
    )
    await db.commit()
    full = await repo.get_navigation_module(db, module_id)
    assert full is not None
    return full


async def delete_module(
    db: AsyncSession,
    module_id: UUID,
    ctx: AuthContext,
) -> None:
    before = await repo.get_navigation_module(db, module_id)
    if not before:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Módulo não encontrado")
    if bool(before.get("is_active")):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Inative o módulo antes de excluí-lo.",
        )
    await repo.delete_navigation_module(db, module_id)
    await repo.insert_navigation_audit(
        db,
        entity_type="navigation_module",
        entity_id=module_id,
        action="delete",
        actor_profile_id=ctx.active_profile_id,
        actor_person_id=ctx.person_id,
        previous_values={"code": before["code"], "name": before["name"]},
        new_values=None,
    )
    await db.commit()


ADMIN_ROLE_CODES = frozenset({
    "platform_admin",
    "admin",
    "administrator",
    "super_admin",
    "coordenador_master",
})


async def get_access_matrix(db: AsyncSession) -> dict:
    return await repo.list_access_matrix(db)


async def update_access_matrix(
    db: AsyncSession,
    updates: list[dict],
    ctx: AuthContext,
) -> dict:
    if not updates:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Nenhuma alteração informada")

    valid_levels = frozenset({"NONE", "VIEW", "EDIT", "MANAGE"})
    for item in updates:
        level = str(item.get("access_level", ""))
        if level not in valid_levels:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Nível inválido: {level}")

    before_count = await repo.count_admin_access_for_roles(db, list(ADMIN_ROLE_CODES))

    for item in updates:
        await repo.upsert_role_module_access(
            db,
            role_definition_id=UUID(str(item["role_definition_id"])),
            navigation_module_id=UUID(str(item["navigation_module_id"])),
            access_level=str(item["access_level"]),
        )

    after_count = await repo.count_admin_access_for_roles(db, list(ADMIN_ROLE_CODES))
    if before_count > 0 and after_count == 0:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Operação bloqueada: removeria todo acesso administrativo ao menu da plataforma.",
        )

    await repo.insert_navigation_audit(
        db,
        entity_type="role_module_access",
        entity_id=ctx.active_profile_id or ctx.person_id,
        action="batch_update",
        actor_profile_id=ctx.active_profile_id,
        actor_person_id=ctx.person_id,
        previous_values={"count": before_count},
        new_values={"updates": len(updates), "admin_access_count": after_count},
    )
    await db.commit()
    return await repo.list_access_matrix(db)

