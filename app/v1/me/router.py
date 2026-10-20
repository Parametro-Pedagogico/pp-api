from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.domains.auth import repository as repo
from app.domains.auth.schemas import ProfileOut
from app.v1.auth.schemas import MeResponseV1, PatchActiveProfileRequestV1, PatchActiveProfileResponseV1
from app.v1.auth.service import apply_active_profile_switch, me_v1
from app.v1.navigation_schemas import NavigationGroupOutV1, NavigationModuleOutV1, UserNavigationOutV1
from app.domains.navigation.service import resolve_user_navigation

router = APIRouter()


@router.get("", response_model=MeResponseV1)
async def get_me_v1(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await me_v1(db, ctx.person_id, ctx.active_profile_id)


@router.get("/profiles", response_model=list[ProfileOut])
async def get_me_profiles_v1(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    rows = await repo.list_profiles_for_person(db, ctx.person_id)
    return [
        ProfileOut.from_row(r)
        for r in rows
    ]


@router.get("/active-profile", response_model=ProfileOut)
async def get_me_active_profile_v1(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    prof = await repo.get_profile_for_person(db, ctx.person_id, ctx.active_profile_id)
    if not prof:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Perfil ativo não encontrado. Entre novamente.")
    return ProfileOut.from_row(prof)


@router.patch("/active-profile", response_model=PatchActiveProfileResponseV1)
async def patch_me_active_profile_v1(
    body: PatchActiveProfileRequestV1,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await apply_active_profile_switch(
        db,
        session_id=ctx.session_id,
        person_id=ctx.person_id,
        new_profile_id=body.profile_id,
    )


@router.get("/navigation", response_model=UserNavigationOutV1)
async def get_me_navigation_v1(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    school_view_id: UUID | None = Query(default=None),
):
    """Menu dinâmico resolvido para o perfil ativo (e visão escola opcional)."""
    data = await resolve_user_navigation(db, ctx, school_view_id=school_view_id)
    groups = [
        NavigationGroupOutV1(
            code=g["code"],
            name=g["name"],
            sort_order=g["sort_order"],
            items=[
                NavigationModuleOutV1(
                    code=i["code"],
                    name=i["name"],
                    route_path=i["route_path"],
                    icon_key=i.get("icon_key"),
                    access_level=i["access_level"],  # type: ignore[arg-type]
                    sort_order=i["sort_order"],
                    match_prefix=i.get("match_prefix", True),
                )
                for i in g["items"]
            ],
        )
        for g in data["groups"]
    ]
    modules = [
        NavigationModuleOutV1(
            code=m["code"],
            name=m["name"],
            route_path=m["route_path"],
            icon_key=m.get("icon_key"),
            access_level=m["access_level"],  # type: ignore[arg-type]
            sort_order=m["sort_order"],
            match_prefix=m.get("match_prefix", True),
        )
        for m in data.get("modules") or []
    ]
    return UserNavigationOutV1(
        version=data["version"],
        effective_role_code=data.get("effective_role_code"),
        groups=groups,
        modules=modules,
    )
