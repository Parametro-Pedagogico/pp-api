"""Administração de auth providers e associações escola-provider."""

from __future__ import annotations

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.domains.auth import providers_repository as repo
from app.v1._scope import is_admin_like
from app.v1._sql import fetch_one
from app.v1.auth.discovery_schemas import (
    AuthProviderCreateV1,
    AuthProviderOutV1,
    AuthProviderUpdateV1,
    SchoolAuthProviderOutV1,
    SchoolAuthProviderUpsertV1,
)

router = APIRouter(prefix="/admin/auth-providers", tags=["v1-auth-providers-admin"])
logger = logging.getLogger(__name__)

VALID_TYPES = frozenset({"PASSWORD", "GOOGLE", "MICROSOFT"})


def _assert_platform_admin(ctx: AuthContext) -> None:
    if not is_admin_like(ctx.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas administradores da plataforma")


def _serialize_provider(row: dict[str, Any]) -> AuthProviderOutV1:
    return AuthProviderOutV1(
        id=UUID(str(row["id"])),
        code=str(row["code"]),
        name=str(row["name"]),
        provider_type=str(row["provider_type"]),
        firebase_provider_id=row.get("firebase_provider_id"),
        is_active=bool(row["is_active"]),
        school_count=int(row["school_count"]) if row.get("school_count") is not None else None,
        created_at=str(row["created_at"]) if row.get("created_at") else None,
        updated_at=str(row["updated_at"]) if row.get("updated_at") else None,
    )


class SchoolSummaryOut(BaseModel):
    id: UUID
    name: str
    code: str
    is_default: bool
    is_active: bool


@router.get("/schools/{school_id}/provider", response_model=SchoolAuthProviderOutV1)
async def get_school_provider(
    school_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    school = await fetch_one(db, "SELECT id FROM schools WHERE id = CAST(:id AS uuid)", {"id": str(school_id)})
    if not school:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Escola não encontrada")
    row = await repo.get_school_auth_provider(db, school_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Escola sem provider configurado")
    return SchoolAuthProviderOutV1(
        id=UUID(str(row["id"])),
        school_id=UUID(str(row["school_id"])),
        auth_provider_id=UUID(str(row["auth_provider_id"])),
        is_active=bool(row["is_active"]),
        is_default=bool(row["is_default"]),
        provider_code=row.get("provider_code"),
        provider_name=row.get("provider_name"),
        provider_type=row.get("provider_type"),
    )


@router.put("/schools/{school_id}/provider", response_model=SchoolAuthProviderOutV1)
async def upsert_school_provider(
    school_id: UUID,
    body: SchoolAuthProviderUpsertV1,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    school = await fetch_one(db, "SELECT id, name FROM schools WHERE id = CAST(:id AS uuid)", {"id": str(school_id)})
    if not school:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Escola não encontrada")
    provider = await repo.get_auth_provider(db, body.auth_provider_id)
    if not provider or not provider.get("is_active"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Provider inválido ou inativo")
    before = await repo.get_school_auth_provider(db, school_id)
    row = await repo.upsert_school_auth_provider(
        db, school_id=school_id, auth_provider_id=body.auth_provider_id
    )
    await repo.insert_audit_log(
        db,
        entity_type="school_auth_provider",
        entity_id=UUID(str(row["id"])),
        action="upsert",
        actor_profile_id=ctx.active_profile_id,
        actor_person_id=ctx.person_id,
        previous_values={
            "auth_provider_id": str(before["auth_provider_id"]) if before else None,
        },
        new_values={"auth_provider_id": str(body.auth_provider_id), "school_id": str(school_id)},
    )
    await db.commit()
    refreshed = await repo.get_school_auth_provider(db, school_id)
    assert refreshed is not None
    return SchoolAuthProviderOutV1(
        id=UUID(str(refreshed["id"])),
        school_id=UUID(str(refreshed["school_id"])),
        auth_provider_id=UUID(str(refreshed["auth_provider_id"])),
        is_active=bool(refreshed["is_active"]),
        is_default=bool(refreshed["is_default"]),
        provider_code=refreshed.get("provider_code"),
        provider_name=refreshed.get("provider_name"),
        provider_type=refreshed.get("provider_type"),
    )


@router.get("", response_model=list[AuthProviderOutV1])
async def list_providers(
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    provider_type: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
):
    _assert_platform_admin(ctx)
    rows = await repo.list_auth_providers(db, provider_type=provider_type, is_active=is_active)
    return [_serialize_provider(r) for r in rows]


@router.get("/{provider_id}", response_model=AuthProviderOutV1)
async def get_provider(
    provider_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    row = await repo.get_auth_provider(db, provider_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider não encontrado")
    count = await repo.count_active_school_associations(db, provider_id)
    row["school_count"] = count
    return _serialize_provider(row)


@router.post("", response_model=AuthProviderOutV1, status_code=status.HTTP_201_CREATED)
async def create_provider(
    body: AuthProviderCreateV1,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    if body.provider_type not in VALID_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tipo de provider inválido")
    existing = await repo.get_auth_provider_by_code(db, body.code)
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Código de provider já existe")
    if body.provider_type in ("GOOGLE", "MICROSOFT") and not body.firebase_provider_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "firebase_provider_id é obrigatório para Google e Microsoft",
        )
    row = await repo.insert_auth_provider(
        db,
        code=body.code,
        name=body.name,
        provider_type=body.provider_type,
        firebase_provider_id=body.firebase_provider_id,
    )
    await repo.insert_audit_log(
        db,
        entity_type="auth_provider",
        entity_id=UUID(str(row["id"])),
        action="create",
        actor_profile_id=ctx.active_profile_id,
        actor_person_id=ctx.person_id,
        previous_values=None,
        new_values={"code": row["code"], "provider_type": row["provider_type"]},
    )
    await db.commit()
    row["school_count"] = 0
    return _serialize_provider(row)


@router.patch("/{provider_id}", response_model=AuthProviderOutV1)
async def update_provider(
    provider_id: UUID,
    body: AuthProviderUpdateV1,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    before = await repo.get_auth_provider(db, provider_id)
    if not before:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider não encontrado")
    if body.is_active is False:
        count = await repo.count_active_school_associations(db, provider_id)
        if count > 0:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Provider associado a {count} escola(s). Inative associações antes ou troque-as.",
            )
    row = await repo.update_auth_provider(
        db,
        provider_id,
        name=body.name,
        firebase_provider_id=body.firebase_provider_id,
        is_active=body.is_active,
    )
    assert row is not None
    await repo.insert_audit_log(
        db,
        entity_type="auth_provider",
        entity_id=provider_id,
        action="update",
        actor_profile_id=ctx.active_profile_id,
        actor_person_id=ctx.person_id,
        previous_values={"name": before["name"], "is_active": before["is_active"]},
        new_values={"name": row["name"], "is_active": row["is_active"]},
    )
    await db.commit()
    row["school_count"] = await repo.count_active_school_associations(db, provider_id)
    return _serialize_provider(row)


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    row = await repo.get_auth_provider(db, provider_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider não encontrado")
    count = await repo.count_active_school_associations(db, provider_id)
    if count > 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Não é permitido excluir provider com escolas associadas. Inative-o.",
        )
    await repo.update_auth_provider(db, provider_id, is_active=False)
    await repo.insert_audit_log(
        db,
        entity_type="auth_provider",
        entity_id=provider_id,
        action="deactivate",
        actor_profile_id=ctx.active_profile_id,
        actor_person_id=ctx.person_id,
        previous_values={"is_active": row["is_active"]},
        new_values={"is_active": False},
    )
    await db.commit()


@router.get("/{provider_id}/schools", response_model=list[SchoolSummaryOut])
async def list_provider_schools(
    provider_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    if not await repo.get_auth_provider(db, provider_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider não encontrado")
    rows = await repo.list_schools_for_provider(db, provider_id)
    return [
        SchoolSummaryOut(
            id=UUID(str(r["id"])),
            name=str(r["name"]),
            code=str(r["code"]),
            is_default=bool(r["is_default"]),
            is_active=bool(r["is_active"]),
        )
        for r in rows
    ]

