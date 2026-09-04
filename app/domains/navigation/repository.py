"""Repositório SQL para grupos e módulos de navegação (admin)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.v1._sql import execute, fetch_all, fetch_one


async def list_navigation_groups(
    db: AsyncSession,
    *,
    include_inactive: bool = True,
) -> list[dict[str, Any]]:
    clause = "" if include_inactive else "WHERE g.is_active = true"
    return await fetch_all(
        db,
        f"""
        SELECT
            g.id,
            g.code,
            g.name,
            g.description,
            g.icon_key,
            g.sort_order,
            g.is_active,
            g.created_at,
            g.updated_at,
            count(m.id) FILTER (WHERE m.is_active) AS module_count
        FROM navigation_groups g
        LEFT JOIN navigation_modules m ON m.group_id = g.id
        {clause}
        GROUP BY g.id
        ORDER BY g.sort_order, g.name
        """,
        {},
    )


async def get_navigation_group(db: AsyncSession, group_id: UUID) -> dict[str, Any] | None:
    return await fetch_one(
        db,
        """
        SELECT id, code, name, description, icon_key, sort_order, is_active, created_at, updated_at
        FROM navigation_groups
        WHERE id = CAST(:id AS uuid)
        """,
        {"id": str(group_id)},
    )


async def get_navigation_group_by_code(db: AsyncSession, code: str) -> dict[str, Any] | None:
    return await fetch_one(
        db,
        """
        SELECT id, code, name, description, icon_key, sort_order, is_active
        FROM navigation_groups WHERE code = :code
        """,
        {"code": code},
    )


async def insert_navigation_group(
    db: AsyncSession,
    *,
    code: str,
    name: str,
    description: str | None,
    icon_key: str | None,
    sort_order: int,
    is_active: bool,
) -> dict[str, Any]:
    row = await fetch_one(
        db,
        """
        INSERT INTO navigation_groups (code, name, description, icon_key, sort_order, is_active)
        VALUES (:code, :name, :description, :icon_key, :sort_order, :is_active)
        RETURNING id, code, name, description, icon_key, sort_order, is_active, created_at, updated_at
        """,
        {
            "code": code,
            "name": name,
            "description": description,
            "icon_key": icon_key,
            "sort_order": sort_order,
            "is_active": is_active,
        },
    )
    assert row is not None
    return row


async def count_modules_in_group(db: AsyncSession, group_id: UUID) -> int:
    row = await fetch_one(
        db,
        """
        SELECT count(*) AS c FROM navigation_modules
        WHERE group_id = CAST(:gid AS uuid)
        """,
        {"gid": str(group_id)},
    )
    return int(row["c"]) if row else 0


async def delete_navigation_group(db: AsyncSession, group_id: UUID) -> None:
    await execute(
        db,
        "DELETE FROM navigation_groups WHERE id = CAST(:id AS uuid)",
        {"id": str(group_id)},
    )


async def delete_navigation_module(db: AsyncSession, module_id: UUID) -> None:
    await execute(
        db,
        "DELETE FROM navigation_modules WHERE id = CAST(:id AS uuid)",
        {"id": str(module_id)},
    )


async def update_navigation_group(
    db: AsyncSession,
    group_id: UUID,
    *,
    name: str | None = None,
    description: str | None = None,
    icon_key: str | None = None,
    sort_order: int | None = None,
    is_active: bool | None = None,
) -> dict[str, Any] | None:
    sets: list[str] = ["updated_at = now()"]
    params: dict[str, Any] = {"id": str(group_id)}
    if name is not None:
        sets.append("name = :name")
        params["name"] = name
    if description is not None:
        sets.append("description = :description")
        params["description"] = description
    if icon_key is not None:
        sets.append("icon_key = :icon_key")
        params["icon_key"] = icon_key
    if sort_order is not None:
        sets.append("sort_order = :sort_order")
        params["sort_order"] = sort_order
    if is_active is not None:
        sets.append("is_active = :is_active")
        params["is_active"] = is_active
    return await fetch_one(
        db,
        f"""
        UPDATE navigation_groups SET {', '.join(sets)}
        WHERE id = CAST(:id AS uuid)
        RETURNING id, code, name, description, icon_key, sort_order, is_active, created_at, updated_at
        """,
        params,
    )


async def list_navigation_modules(
    db: AsyncSession,
    *,
    group_id: UUID | None = None,
    include_inactive: bool = True,
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: dict[str, Any] = {}
    if group_id:
        clauses.append("m.group_id = CAST(:group_id AS uuid)")
        params["group_id"] = str(group_id)
    if not include_inactive:
        clauses.append("m.is_active = true")
    return await fetch_all(
        db,
        f"""
        SELECT
            m.id,
            m.group_id,
            g.code AS group_code,
            g.name AS group_name,
            m.code,
            m.name,
            m.description,
            m.route_path,
            m.destination_type,
            m.icon_key,
            m.sort_order,
            m.is_active,
            m.match_prefix,
            m.required_feature_flag,
            m.open_in_new_tab,
            m.created_at,
            m.updated_at
        FROM navigation_modules m
        JOIN navigation_groups g ON g.id = m.group_id
        WHERE {' AND '.join(clauses)}
        ORDER BY g.sort_order, m.sort_order, m.name
        """,
        params,
    )


async def get_navigation_module(db: AsyncSession, module_id: UUID) -> dict[str, Any] | None:
    return await fetch_one(
        db,
        """
        SELECT
            m.id, m.group_id, g.code AS group_code, m.code, m.name, m.description,
            m.route_path, m.destination_type, m.icon_key, m.sort_order, m.is_active,
            m.match_prefix, m.required_feature_flag, m.open_in_new_tab,
            m.created_at, m.updated_at
        FROM navigation_modules m
        JOIN navigation_groups g ON g.id = m.group_id
        WHERE m.id = CAST(:id AS uuid)
        """,
        {"id": str(module_id)},
    )


async def insert_navigation_module(
    db: AsyncSession,
    *,
    group_id: UUID,
    code: str,
    name: str,
    description: str | None,
    route_path: str,
    icon_key: str | None,
    sort_order: int,
    is_active: bool,
    match_prefix: bool,
    required_feature_flag: str | None,
) -> dict[str, Any]:
    row = await fetch_one(
        db,
        """
        INSERT INTO navigation_modules (
            group_id, code, name, description, route_path, icon_key, sort_order,
            is_active, match_prefix, required_feature_flag
        )
        VALUES (
            CAST(:group_id AS uuid), :code, :name, :description, :route_path, :icon_key,
            :sort_order, :is_active, :match_prefix, :required_feature_flag
        )
        RETURNING id, group_id, code, name, description, route_path, icon_key, sort_order,
                  is_active, match_prefix, required_feature_flag, open_in_new_tab,
                  created_at, updated_at
        """,
        {
            "group_id": str(group_id),
            "code": code,
            "name": name,
            "description": description,
            "route_path": route_path,
            "icon_key": icon_key,
            "sort_order": sort_order,
            "is_active": is_active,
            "match_prefix": match_prefix,
            "required_feature_flag": required_feature_flag,
        },
    )
    assert row is not None
    return row


async def update_navigation_module(
    db: AsyncSession,
    module_id: UUID,
    *,
    group_id: UUID | None = None,
    name: str | None = None,
    description: str | None = None,
    route_path: str | None = None,
    icon_key: str | None = None,
    sort_order: int | None = None,
    is_active: bool | None = None,
    match_prefix: bool | None = None,
    required_feature_flag: str | None = None,
) -> dict[str, Any] | None:
    sets: list[str] = ["updated_at = now()"]
    params: dict[str, Any] = {"id": str(module_id)}
    if group_id is not None:
        sets.append("group_id = CAST(:group_id AS uuid)")
        params["group_id"] = str(group_id)
    if name is not None:
        sets.append("name = :name")
        params["name"] = name
    if description is not None:
        sets.append("description = :description")
        params["description"] = description
    if route_path is not None:
        sets.append("route_path = :route_path")
        params["route_path"] = route_path
    if icon_key is not None:
        sets.append("icon_key = :icon_key")
        params["icon_key"] = icon_key
    if sort_order is not None:
        sets.append("sort_order = :sort_order")
        params["sort_order"] = sort_order
    if is_active is not None:
        sets.append("is_active = :is_active")
        params["is_active"] = is_active
    if match_prefix is not None:
        sets.append("match_prefix = :match_prefix")
        params["match_prefix"] = match_prefix
    if required_feature_flag is not None:
        sets.append("required_feature_flag = :required_feature_flag")
        params["required_feature_flag"] = required_feature_flag
    return await fetch_one(
        db,
        f"""
        UPDATE navigation_modules SET {', '.join(sets)}
        WHERE id = CAST(:id AS uuid)
        RETURNING id, group_id, code, name, description, route_path, icon_key, sort_order,
                  is_active, match_prefix, required_feature_flag, open_in_new_tab,
                  created_at, updated_at
        """,
        params,
    )


async def insert_navigation_audit(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: UUID,
    action: str,
    actor_profile_id: UUID | None,
    actor_person_id: UUID | None,
    previous_values: dict | None,
    new_values: dict | None,
) -> None:
    import json

    await execute(
        db,
        """
        INSERT INTO navigation_audit_log (
            entity_type, entity_id, action, actor_profile_id, actor_person_id,
            previous_values, new_values
        )
        VALUES (
            :entity_type, CAST(:entity_id AS uuid), :action,
            CAST(:actor_profile_id AS uuid), CAST(:actor_person_id AS uuid),
            CAST(:previous_values AS jsonb), CAST(:new_values AS jsonb)
        )
        """,
        {
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "action": action,
            "actor_profile_id": str(actor_profile_id) if actor_profile_id else None,
            "actor_person_id": str(actor_person_id) if actor_person_id else None,
            "previous_values": json.dumps(previous_values) if previous_values else None,
            "new_values": json.dumps(new_values) if new_values else None,
        },
    )


async def max_group_sort_order(db: AsyncSession) -> int:
    row = await fetch_one(db, "SELECT coalesce(max(sort_order), 0) AS m FROM navigation_groups", {})
    return int(row["m"]) if row else 0


async def max_module_sort_order(db: AsyncSession, group_id: UUID) -> int:
    row = await fetch_one(
        db,
        """
        SELECT coalesce(max(sort_order), 0) AS m FROM navigation_modules
        WHERE group_id = CAST(:gid AS uuid)
        """,
        {"gid": str(group_id)},
    )
    return int(row["m"]) if row else 0


async def list_access_matrix(db: AsyncSession) -> dict:
    roles = await fetch_all(
        db,
        """
        SELECT id, code, name, sort_order, is_active
        FROM role_definitions
        ORDER BY sort_order, name
        """,
        {},
    )
    modules = await fetch_all(
        db,
        """
        SELECT
            m.id,
            m.code,
            m.name,
            m.group_id,
            g.code AS group_code,
            g.name AS group_name,
            g.sort_order AS group_sort_order,
            m.sort_order,
            m.is_active
        FROM navigation_modules m
        JOIN navigation_groups g ON g.id = m.group_id
        ORDER BY g.sort_order, m.sort_order, m.name
        """,
        {},
    )
    access = await fetch_all(
        db,
        """
        SELECT role_definition_id, navigation_module_id, access_level
        FROM role_module_access
        WHERE is_active = true
        """,
        {},
    )
    return {"roles": roles, "modules": modules, "access": access}


async def upsert_role_module_access(
    db: AsyncSession,
    *,
    role_definition_id: UUID,
    navigation_module_id: UUID,
    access_level: str,
) -> None:
    existing = await fetch_one(
        db,
        """
        SELECT id FROM role_module_access
        WHERE role_definition_id = CAST(:rid AS uuid)
          AND navigation_module_id = CAST(:mid AS uuid)
        """,
        {"rid": str(role_definition_id), "mid": str(navigation_module_id)},
    )
    if existing:
        await execute(
            db,
            """
            UPDATE role_module_access
            SET access_level = :level, is_active = true, updated_at = now()
            WHERE id = CAST(:id AS uuid)
            """,
            {"id": str(existing["id"]), "level": access_level},
        )
    else:
        await execute(
            db,
            """
            INSERT INTO role_module_access (role_definition_id, navigation_module_id, access_level)
            VALUES (CAST(:rid AS uuid), CAST(:mid AS uuid), :level)
            """,
            {"rid": str(role_definition_id), "mid": str(navigation_module_id), "level": access_level},
        )


async def count_admin_access_for_roles(db: AsyncSession, role_codes: list[str]) -> int:
    row = await fetch_one(
        db,
        """
        SELECT count(*) AS c
        FROM role_module_access rma
        JOIN role_definitions rd ON rd.id = rma.role_definition_id
        JOIN navigation_modules m ON m.id = rma.navigation_module_id
        WHERE rd.code = ANY(:codes)
          AND rma.is_active = true
          AND rma.access_level <> 'NONE'
          AND m.code LIKE 'admin.%'
        """,
        {"codes": role_codes},
    )
    return int(row["c"]) if row else 0

