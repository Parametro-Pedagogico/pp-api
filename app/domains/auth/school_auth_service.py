"""Configuração de autenticação por escola (multi-provider + herança da rede)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.auth import providers_repository as repo
from app.v1._sql import fetch_one


async def _get_school_row(db: AsyncSession, school_id: UUID) -> dict[str, Any]:
    row = await fetch_one(
        db,
        """
        SELECT s.id, s.name, s.code, s.parent, s.auth_inherit_from_parent,
               p.name AS parent_name
        FROM schools s
        LEFT JOIN schools p ON p.id = s.parent
        WHERE s.id = CAST(:id AS uuid)
        """,
        {"id": str(school_id)},
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Escola não encontrada")
    return row


async def _resolve_chain_providers(
    db: AsyncSession,
    school_id: UUID,
    *,
    _visited: set[UUID] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    visited = _visited or set()
    if school_id in visited:
        return [], None
    visited.add(school_id)

    school = await _get_school_row(db, school_id)

    if school.get("auth_inherit_from_parent") and school.get("parent"):
        parent_id = UUID(str(school["parent"]))
        rows, source = await _resolve_chain_providers(db, parent_id, _visited=visited)
        if rows:
            origin = source or {
                "school_id": parent_id,
                "display_name": school.get("parent_name") or "Rede",
            }
            return rows, origin

    local = await repo.list_local_school_auth_providers(db, school_id, active_only=True)
    if local:
        return local, None

    password = await repo.get_auth_provider_by_code(db, "password")
    if password:
        return [
            {
                "auth_provider_id": password["id"],
                "code": password["code"],
                "name": password["name"],
                "provider_type": password["provider_type"],
                "is_active": True,
            }
        ], None

    return [], None


async def get_school_auth_config(db: AsyncSession, school_id: UUID) -> dict[str, Any]:
    school = await _get_school_row(db, school_id)
    catalog = await repo.list_auth_providers(db, is_active=True)
    local_rows = await repo.list_local_school_auth_providers(db, school_id, active_only=False)
    local_by_provider = {str(r["auth_provider_id"]): r for r in local_rows}

    inherit = bool(school.get("auth_inherit_from_parent"))
    inherited_from: dict[str, Any] | None = None
    effective: list[dict[str, Any]] = []

    if inherit and school.get("parent"):
        effective, chain_source = await _resolve_chain_providers(db, UUID(str(school["parent"])))
        inherited_from = chain_source or {
            "school_id": UUID(str(school["parent"])),
            "display_name": school.get("parent_name") or "Rede",
        }
    elif not inherit:
        effective = [r for r in local_rows if r.get("is_active")]
    else:
        effective, _ = await _resolve_chain_providers(db, school_id)

    effective_ids = {str(r["auth_provider_id"]) for r in effective}

    providers: list[dict[str, Any]] = []
    for item in catalog:
        pid = str(item["id"])
        local = local_by_provider.get(pid)
        if inherit:
            is_active = pid in effective_ids
            source = "inherited" if is_active else "inactive"
        else:
            is_active = bool(local and local.get("is_active"))
            source = "local" if is_active else "inactive"

        providers.append(
            {
                "auth_provider_id": item["id"],
                "code": item["code"],
                "name": item["name"],
                "provider_type": item["provider_type"],
                "is_active": is_active,
                "has_local_row": local is not None,
                "source": source,
            }
        )

    return {
        "school_id": school_id,
        "school_name": school["name"],
        "parent_id": school.get("parent"),
        "parent_name": school.get("parent_name"),
        "auth_inherit_from_parent": inherit,
        "inherited_from": inherited_from,
        "effective_methods": sorted(
            {
                repo.PROVIDER_TYPE_TO_METHOD.get(str(r["provider_type"]), "password")
                for r in effective
            }
        ),
        "providers": providers,
    }


async def set_school_auth_config(
    db: AsyncSession,
    school_id: UUID,
    *,
    auth_inherit_from_parent: bool,
    active_provider_ids: list[UUID],
    actor_profile_id: UUID | None,
    actor_person_id: UUID | None,
) -> dict[str, Any]:
    school = await _get_school_row(db, school_id)
    catalog = await repo.list_auth_providers(db, is_active=True)
    catalog_ids = {UUID(str(c["id"])) for c in catalog}

    if not auth_inherit_from_parent:
        active_set = set(active_provider_ids)
        if active_set - catalog_ids:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Provider inválido")
        if not active_set:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Pelo menos um método de autenticação deve permanecer ativo.",
            )

    await repo.update_school_auth_inherit(db, school_id, auth_inherit_from_parent)

    if not auth_inherit_from_parent:
        await repo.sync_school_auth_providers(
            db,
            school_id=school_id,
            active_provider_ids=active_provider_ids,
        )

    await repo.insert_audit_log(
        db,
        entity_type="school_auth_config",
        entity_id=school_id,
        action="update",
        actor_profile_id=actor_profile_id,
        actor_person_id=actor_person_id,
        previous_values={
            "auth_inherit_from_parent": bool(school.get("auth_inherit_from_parent")),
        },
        new_values={
            "auth_inherit_from_parent": auth_inherit_from_parent,
            "active_provider_ids": [str(x) for x in active_provider_ids],
        },
    )
    await db.commit()
    return await get_school_auth_config(db, school_id)


async def resolve_school_auth_methods(db: AsyncSession, school_id: UUID) -> list[dict[str, Any]]:
    school = await _get_school_row(db, school_id)
    if school.get("auth_inherit_from_parent") and school.get("parent"):
        rows, _ = await _resolve_chain_providers(db, UUID(str(school["parent"])))
    else:
        rows = await repo.list_local_school_auth_providers(db, school_id, active_only=True)
        if not rows:
            rows, _ = await _resolve_chain_providers(db, school_id)

    display_name = str(school["name"])
    methods: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        method = repo.PROVIDER_TYPE_TO_METHOD.get(str(row["provider_type"]), "password")
        if method in seen:
            continue
        seen.add(method)
        methods.append(
            {
                "school_id": school_id,
                "display_name": display_name,
                "method": method,
                "provider_type": row["provider_type"],
            }
        )
    return methods
