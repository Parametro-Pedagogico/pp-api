"""Repositório SQL para role_definitions."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.v1._sql import fetch_all, fetch_one


async def resolve_role_definition(db: AsyncSession, role_raw: str) -> dict[str, Any] | None:
    normalized = (role_raw or "").strip().lower().replace("-", "_")
    if not normalized:
        return None
    row = await fetch_one(
        db,
        """
        SELECT id, code, name, scope_type, is_system, is_active, sort_order
        FROM role_definitions
        WHERE code = :code AND is_active = true
        """,
        {"code": normalized},
    )
    if row:
        return row
    return await fetch_one(
        db,
        """
        SELECT rd.id, rd.code, rd.name, rd.scope_type, rd.is_system, rd.is_active, rd.sort_order
        FROM role_definition_aliases a
        JOIN role_definitions rd ON rd.id = a.role_definition_id
        WHERE lower(a.alias) = :alias AND rd.is_active = true
        """,
        {"alias": normalized},
    )


async def get_role_definition_by_code(db: AsyncSession, code: str) -> dict[str, Any] | None:
    return await fetch_one(
        db,
        """
        SELECT id, code, name, description, scope_type, is_system, is_active, sort_order,
               created_at, updated_at
        FROM role_definitions
        WHERE code = :code
        """,
        {"code": code},
    )


async def list_role_definitions(
    db: AsyncSession,
    *,
    is_active: bool | None = None,
    assignable_only: bool = False,
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: dict[str, Any] = {}
    if is_active is not None:
        clauses.append("is_active = :is_active")
        params["is_active"] = is_active
    if assignable_only:
        clauses.append("is_active = true")
    return await fetch_all(
        db,
        f"""
        SELECT id, code, name, description, scope_type, is_system, is_active, sort_order,
               created_at, updated_at
        FROM role_definitions
        WHERE {' AND '.join(clauses)}
        ORDER BY sort_order, name
        """,
        params,
    )


async def get_role_definition(db: AsyncSession, role_id: UUID) -> dict[str, Any] | None:
    return await fetch_one(
        db,
        """
        SELECT id, code, name, description, scope_type, is_system, is_active, sort_order,
               created_at, updated_at
        FROM role_definitions
        WHERE id = CAST(:id AS uuid)
        """,
        {"id": str(role_id)},
    )


async def list_role_definitions_with_aliases(
    db: AsyncSession,
    *,
    is_active: bool | None = None,
    assignable_only: bool = False,
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: dict[str, Any] = {}
    if is_active is not None:
        clauses.append("rd.is_active = :is_active")
        params["is_active"] = is_active
    if assignable_only:
        clauses.append("rd.is_active = true")
        clauses.append("rd.code NOT IN ('admin', 'administrator', 'super_admin', 'coordenador_master')")
    return await fetch_all(
        db,
        f"""
        SELECT
            rd.id,
            rd.code,
            rd.name,
            rd.description,
            rd.scope_type,
            rd.is_system,
            rd.is_active,
            rd.sort_order,
            rd.created_at,
            rd.updated_at,
            coalesce(
                array_agg(a.alias ORDER BY a.alias) FILTER (WHERE a.id IS NOT NULL),
                ARRAY[]::varchar[]
            ) AS aliases
        FROM role_definitions rd
        LEFT JOIN role_definition_aliases a ON a.role_definition_id = rd.id
        WHERE {' AND '.join(clauses)}
        GROUP BY rd.id
        ORDER BY rd.sort_order, rd.name
        """,
        params,
    )


async def list_aliases_for_role(db: AsyncSession, role_id: UUID) -> list[str]:
    rows = await fetch_all(
        db,
        """
        SELECT alias FROM role_definition_aliases
        WHERE role_definition_id = CAST(:id AS uuid)
        ORDER BY alias
        """,
        {"id": str(role_id)},
    )
    return [str(r["alias"]) for r in rows]


async def max_role_sort_order(db: AsyncSession) -> int:
    row = await fetch_one(
        db,
        "SELECT coalesce(max(sort_order), 0) AS m FROM role_definitions",
        {},
    )
    return int(row["m"]) if row else 0


async def insert_role_definition(
    db: AsyncSession,
    *,
    code: str,
    name: str,
    description: str | None,
    scope_type: str,
    sort_order: int,
    is_active: bool,
) -> dict[str, Any]:
    row = await fetch_one(
        db,
        """
        INSERT INTO role_definitions (code, name, description, scope_type, is_system, is_active, sort_order)
        VALUES (:code, :name, :description, :scope_type, false, :is_active, :sort_order)
        RETURNING id, code, name, description, scope_type, is_system, is_active, sort_order,
                  created_at, updated_at
        """,
        {
            "code": code,
            "name": name,
            "description": description,
            "scope_type": scope_type,
            "is_active": is_active,
            "sort_order": sort_order,
        },
    )
    assert row is not None
    return row


async def update_role_definition(
    db: AsyncSession,
    role_id: UUID,
    *,
    name: str | None = None,
    description: str | None = None,
    scope_type: str | None = None,
    sort_order: int | None = None,
    is_active: bool | None = None,
) -> dict[str, Any] | None:
    sets: list[str] = ["updated_at = now()"]
    params: dict[str, Any] = {"id": str(role_id)}
    if name is not None:
        sets.append("name = :name")
        params["name"] = name
    if description is not None:
        sets.append("description = :description")
        params["description"] = description
    if scope_type is not None:
        sets.append("scope_type = :scope_type")
        params["scope_type"] = scope_type
    if sort_order is not None:
        sets.append("sort_order = :sort_order")
        params["sort_order"] = sort_order
    if is_active is not None:
        sets.append("is_active = :is_active")
        params["is_active"] = is_active
    if len(sets) == 1:
        return await get_role_definition(db, role_id)
    return await fetch_one(
        db,
        f"""
        UPDATE role_definitions
        SET {', '.join(sets)}
        WHERE id = CAST(:id AS uuid)
        RETURNING id, code, name, description, scope_type, is_system, is_active, sort_order,
                  created_at, updated_at
        """,
        params,
    )


async def count_profiles_for_role_definition(db: AsyncSession, role_id: UUID) -> int:
    row = await fetch_one(
        db,
        """
        SELECT count(*) AS c FROM profiles
        WHERE role_definition_id = CAST(:id AS uuid)
        """,
        {"id": str(role_id)},
    )
    return int(row["c"]) if row else 0


async def count_profiles_linked_to_role(
    db: AsyncSession,
    role_id: UUID,
    role_code: str,
) -> int:
    row = await fetch_one(
        db,
        """
        SELECT count(DISTINCT p.id) AS c
        FROM profiles p
        WHERE p.role_definition_id = CAST(:id AS uuid)
           OR lower(replace(p.role::text, '-', '_')) = :code
           OR EXISTS (
                SELECT 1
                FROM role_definition_aliases a
                WHERE a.role_definition_id = CAST(:id AS uuid)
                  AND lower(replace(p.role::text, '-', '_')) = lower(replace(a.alias, '-', '_'))
           )
        """,
        {"id": str(role_id), "code": role_code.lower()},
    )
    return int(row["c"]) if row else 0


async def delete_role_definition(db: AsyncSession, role_id: UUID) -> None:
    await fetch_one(
        db,
        """
        DELETE FROM role_definitions
        WHERE id = CAST(:id AS uuid)
        RETURNING id
        """,
        {"id": str(role_id)},
    )


async def count_profiles_for_role_code(db: AsyncSession, role_code: str) -> int:
    enum_map = {
        "student": "STUDENT",
        "teacher": "TEACHER",
        "school_admin": "SCHOOL_ADMIN",
        "platform_admin": "PLATFORM_ADMIN",
    }
    enum_val = enum_map.get(role_code)
    if not enum_val:
        row = await fetch_one(
            db,
            """
            SELECT count(*) AS c FROM profiles
            WHERE lower(replace(role::text, '-', '_')) = :code
            """,
            {"code": role_code.lower()},
        )
    else:
        row = await fetch_one(
            db,
            """
            SELECT count(*) AS c FROM profiles
            WHERE role = CAST(:role AS user_role)
            """,
            {"role": enum_val},
        )
    return int(row["c"]) if row else 0

