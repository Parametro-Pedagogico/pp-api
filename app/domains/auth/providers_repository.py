"""Repositório SQL para auth_providers e school_auth_providers."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.v1._sql import execute, fetch_all, fetch_one


PROVIDER_TYPE_TO_METHOD = {
    "PASSWORD": "password",
    "GOOGLE": "google",
    "MICROSOFT": "microsoft",
}

METHOD_TO_PROVIDER_TYPE = {v: k for k, v in PROVIDER_TYPE_TO_METHOD.items()}


async def list_auth_providers(
    db: AsyncSession,
    *,
    provider_type: str | None = None,
    is_active: bool | None = None,
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: dict[str, Any] = {}
    if provider_type:
        clauses.append("ap.provider_type = :provider_type")
        params["provider_type"] = provider_type.upper()
    if is_active is not None:
        clauses.append("ap.is_active = :is_active")
        params["is_active"] = is_active
    sql = f"""
        SELECT
            ap.id,
            ap.code,
            ap.name,
            ap.provider_type,
            ap.firebase_provider_id,
            ap.is_active,
            ap.created_at,
            ap.updated_at,
            COALESCE(sc.cnt, 0) AS school_count
        FROM auth_providers ap
        LEFT JOIN (
            SELECT auth_provider_id, COUNT(*) AS cnt
            FROM school_auth_providers
            WHERE is_active = true
            GROUP BY auth_provider_id
        ) sc ON sc.auth_provider_id = ap.id
        WHERE {' AND '.join(clauses)}
        ORDER BY ap.name
    """
    return await fetch_all(db, sql, params)


async def get_auth_provider(db: AsyncSession, provider_id: UUID) -> dict[str, Any] | None:
    return await fetch_one(
        db,
        """
        SELECT id, code, name, provider_type, firebase_provider_id, is_active, created_at, updated_at
        FROM auth_providers
        WHERE id = CAST(:id AS uuid)
        """,
        {"id": str(provider_id)},
    )


async def get_auth_provider_by_code(db: AsyncSession, code: str) -> dict[str, Any] | None:
    return await fetch_one(
        db,
        """
        SELECT id, code, name, provider_type, firebase_provider_id, is_active
        FROM auth_providers
        WHERE code = :code
        """,
        {"code": code},
    )


async def insert_auth_provider(
    db: AsyncSession,
    *,
    code: str,
    name: str,
    provider_type: str,
    firebase_provider_id: str | None,
) -> dict[str, Any]:
    row = await fetch_one(
        db,
        """
        INSERT INTO auth_providers (code, name, provider_type, firebase_provider_id, is_active)
        VALUES (:code, :name, :provider_type, :firebase_provider_id, true)
        RETURNING id, code, name, provider_type, firebase_provider_id, is_active, created_at, updated_at
        """,
        {
            "code": code,
            "name": name,
            "provider_type": provider_type.upper(),
            "firebase_provider_id": firebase_provider_id,
        },
    )
    assert row is not None
    return row


async def update_auth_provider(
    db: AsyncSession,
    provider_id: UUID,
    *,
    name: str | None = None,
    firebase_provider_id: str | None = None,
    is_active: bool | None = None,
) -> dict[str, Any] | None:
    fields: list[str] = []
    params: dict[str, Any] = {"id": str(provider_id)}
    if name is not None:
        fields.append("name = :name")
        params["name"] = name
    if firebase_provider_id is not None:
        fields.append("firebase_provider_id = :firebase_provider_id")
        params["firebase_provider_id"] = firebase_provider_id or None
    if is_active is not None:
        fields.append("is_active = :is_active")
        params["is_active"] = is_active
    if not fields:
        return await get_auth_provider(db, provider_id)
    fields.append("updated_at = now()")
    sql = f"""
        UPDATE auth_providers
        SET {', '.join(fields)}
        WHERE id = CAST(:id AS uuid)
        RETURNING id, code, name, provider_type, firebase_provider_id, is_active, created_at, updated_at
    """
    return await fetch_one(db, sql, params)


async def count_active_school_associations(db: AsyncSession, provider_id: UUID) -> int:
    row = await fetch_one(
        db,
        """
        SELECT COUNT(*) AS cnt
        FROM school_auth_providers
        WHERE auth_provider_id = CAST(:id AS uuid) AND is_active = true
        """,
        {"id": str(provider_id)},
    )
    return int(row["cnt"]) if row else 0


async def list_schools_for_provider(db: AsyncSession, provider_id: UUID) -> list[dict[str, Any]]:
    return await fetch_all(
        db,
        """
        SELECT s.id, s.name, s.code, sap.is_default, sap.is_active
        FROM school_auth_providers sap
        JOIN schools s ON s.id = sap.school_id
        WHERE sap.auth_provider_id = CAST(:id AS uuid)
        ORDER BY s.name
        """,
        {"id": str(provider_id)},
    )


async def list_local_school_auth_providers(
    db: AsyncSession,
    school_id: UUID,
    *,
    active_only: bool = False,
) -> list[dict[str, Any]]:
    clauses = ["sap.school_id = CAST(:school_id AS uuid)"]
    if active_only:
        clauses.append("sap.is_active = true")
        clauses.append("ap.is_active = true")
    sql = f"""
        SELECT
            sap.id,
            sap.school_id,
            sap.auth_provider_id,
            sap.is_active,
            sap.is_default,
            ap.code,
            ap.name,
            ap.provider_type,
            ap.is_active AS catalog_is_active
        FROM school_auth_providers sap
        JOIN auth_providers ap ON ap.id = sap.auth_provider_id
        WHERE {' AND '.join(clauses)}
        ORDER BY ap.name
    """
    return await fetch_all(db, sql, {"school_id": str(school_id)})


async def update_school_auth_inherit(
    db: AsyncSession,
    school_id: UUID,
    inherit: bool,
) -> None:
    await execute(
        db,
        """
        UPDATE schools
        SET auth_inherit_from_parent = :inherit, updated_at = now()
        WHERE id = CAST(:id AS uuid)
        """,
        {"id": str(school_id), "inherit": inherit},
    )


async def sync_school_auth_providers(
    db: AsyncSession,
    *,
    school_id: UUID,
    active_provider_ids: list[UUID],
) -> None:
    catalog = await list_auth_providers(db, is_active=True)
    active_set = {str(pid) for pid in active_provider_ids}
    first_default = str(active_provider_ids[0]) if active_provider_ids else None

    for item in catalog:
        pid = str(item["id"])
        is_active = pid in active_set
        is_default = pid == first_default
        existing = await fetch_one(
            db,
            """
            SELECT id FROM school_auth_providers
            WHERE school_id = CAST(:school_id AS uuid)
              AND auth_provider_id = CAST(:provider_id AS uuid)
            """,
            {"school_id": str(school_id), "provider_id": pid},
        )
        if existing:
            await execute(
                db,
                """
                UPDATE school_auth_providers
                SET is_active = :is_active, is_default = :is_default, updated_at = now()
                WHERE id = CAST(:id AS uuid)
                """,
                {
                    "id": str(existing["id"]),
                    "is_active": is_active,
                    "is_default": is_default and is_active,
                },
            )
        elif is_active:
            await execute(
                db,
                """
                INSERT INTO school_auth_providers (school_id, auth_provider_id, is_active, is_default)
                VALUES (CAST(:school_id AS uuid), CAST(:provider_id AS uuid), true, :is_default)
                """,
                {
                    "school_id": str(school_id),
                    "provider_id": pid,
                    "is_default": is_default,
                },
            )


async def ensure_default_password_for_school(db: AsyncSession, school_id: UUID) -> None:
    password = await get_auth_provider_by_code(db, "password")
    if not password:
        return
    await sync_school_auth_providers(
        db,
        school_id=school_id,
        active_provider_ids=[UUID(str(password["id"]))],
    )


async def get_school_auth_provider(db: AsyncSession, school_id: UUID) -> dict[str, Any] | None:
    return await fetch_one(
        db,
        """
        SELECT
            sap.id,
            sap.school_id,
            sap.auth_provider_id,
            sap.is_active,
            sap.is_default,
            ap.code AS provider_code,
            ap.name AS provider_name,
            ap.provider_type,
            ap.firebase_provider_id
        FROM school_auth_providers sap
        JOIN auth_providers ap ON ap.id = sap.auth_provider_id
        WHERE sap.school_id = CAST(:school_id AS uuid)
          AND sap.is_active = true
          AND sap.is_default = true
          AND ap.is_active = true
        LIMIT 1
        """,
        {"school_id": str(school_id)},
    )


async def get_default_provider_for_school(db: AsyncSession, school_id: UUID) -> dict[str, Any] | None:
    return await get_school_auth_provider(db, school_id)


async def upsert_school_auth_provider(
    db: AsyncSession,
    *,
    school_id: UUID,
    auth_provider_id: UUID,
) -> dict[str, Any]:
    """Substitui transacionalmente o provider padrão ativo da escola."""
    await execute(
        db,
        """
        UPDATE school_auth_providers
        SET is_default = false, is_active = false, updated_at = now()
        WHERE school_id = CAST(:school_id AS uuid) AND is_active = true
        """,
        {"school_id": str(school_id)},
    )
    existing = await fetch_one(
        db,
        """
        SELECT id FROM school_auth_providers
        WHERE school_id = CAST(:school_id AS uuid)
          AND auth_provider_id = CAST(:provider_id AS uuid)
        """,
        {"school_id": str(school_id), "provider_id": str(auth_provider_id)},
    )
    if existing:
        row = await fetch_one(
            db,
            """
            UPDATE school_auth_providers
            SET is_active = true, is_default = true, updated_at = now()
            WHERE id = CAST(:id AS uuid)
            RETURNING id, school_id, auth_provider_id, is_active, is_default
            """,
            {"id": str(existing["id"])},
        )
    else:
        row = await fetch_one(
            db,
            """
            INSERT INTO school_auth_providers (school_id, auth_provider_id, is_active, is_default)
            VALUES (CAST(:school_id AS uuid), CAST(:provider_id AS uuid), true, true)
            RETURNING id, school_id, auth_provider_id, is_active, is_default
            """,
            {"school_id": str(school_id), "provider_id": str(auth_provider_id)},
        )
    assert row is not None
    return row


async def insert_audit_log(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: UUID,
    action: str,
    actor_profile_id: UUID | None,
    actor_person_id: UUID | None,
    previous_values: dict | None,
    new_values: dict | None,
    result: str = "success",
) -> None:
    import json

    await execute(
        db,
        """
        INSERT INTO auth_provider_audit_log (
            entity_type, entity_id, action, actor_profile_id, actor_person_id,
            previous_values, new_values, result
        )
        VALUES (
            :entity_type, CAST(:entity_id AS uuid), :action,
            CAST(:actor_profile_id AS uuid), CAST(:actor_person_id AS uuid),
            CAST(:previous_values AS jsonb), CAST(:new_values AS jsonb), :result
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
            "result": result,
        },
    )
