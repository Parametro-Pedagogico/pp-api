"""Configurações administrativas por escola."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.domains.auth import school_auth_service as school_auth
from app.v1._scope import is_admin_like
from app.v1.school_settings_schemas import (
    SchoolAuthConfigOutV1,
    SchoolAuthConfigUpdateV1,
    SchoolAuthInheritedFromV1,
    SchoolAuthProviderItemV1,
)

router = APIRouter(prefix="/admin/schools", tags=["v1-school-settings"])


def _assert_platform_admin(ctx: AuthContext) -> None:
    if not is_admin_like(ctx.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas administradores da plataforma")


def _serialize_auth_config(data: dict) -> SchoolAuthConfigOutV1:
    inherited = data.get("inherited_from")
    return SchoolAuthConfigOutV1(
        school_id=UUID(str(data["school_id"])),
        school_name=str(data["school_name"]),
        parent_id=UUID(str(data["parent_id"])) if data.get("parent_id") else None,
        parent_name=data.get("parent_name"),
        auth_inherit_from_parent=bool(data["auth_inherit_from_parent"]),
        inherited_from=(
            SchoolAuthInheritedFromV1(
                school_id=UUID(str(inherited["school_id"])),
                display_name=str(inherited["display_name"]),
            )
            if inherited
            else None
        ),
        effective_methods=list(data.get("effective_methods") or []),
        providers=[
            SchoolAuthProviderItemV1(
                auth_provider_id=UUID(str(p["auth_provider_id"])),
                code=str(p["code"]),
                name=str(p["name"]),
                provider_type=str(p["provider_type"]),
                is_active=bool(p["is_active"]),
                has_local_row=bool(p["has_local_row"]),
                source=p["source"],  # type: ignore[arg-type]
            )
            for p in data.get("providers") or []
        ],
    )


@router.get("/{school_id}/settings/auth", response_model=SchoolAuthConfigOutV1)
async def get_school_auth_settings(
    school_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    data = await school_auth.get_school_auth_config(db, school_id)
    return _serialize_auth_config(data)


@router.put("/{school_id}/settings/auth", response_model=SchoolAuthConfigOutV1)
async def update_school_auth_settings(
    school_id: UUID,
    body: SchoolAuthConfigUpdateV1,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    data = await school_auth.set_school_auth_config(
        db,
        school_id,
        auth_inherit_from_parent=body.auth_inherit_from_parent,
        active_provider_ids=body.active_provider_ids,
        actor_profile_id=ctx.active_profile_id,
        actor_person_id=ctx.person_id,
    )
    return _serialize_auth_config(data)
