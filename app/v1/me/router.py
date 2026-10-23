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
from app.v1._scope import get_effective_classroom_scope
from app.v1._sql import fetch_all

router = APIRouter()


def _schedule_item(r: dict) -> dict:
    return {
        "schedule_id": str(r["schedule_id"]),
        "macro_assessment_id": str(r["macro_assessment_id"]) if r.get("macro_assessment_id") else None,
        "classroom_id": str(r["classroom_id"]) if r.get("classroom_id") else None,
        "assessment_title": r.get("assessment_title") or "Aplicação",
        "classroom_name": r.get("classroom_name"),
        "school_name": r.get("school_name"),
        "start_time": r["start_time"].isoformat() if r.get("start_time") else None,
        "end_time": r["end_time"].isoformat() if r.get("end_time") else None,
    }


@router.get("/inicio")
async def get_me_inicio_v1(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """(Fase 4) Tela inicial do perfil ativo: pendências, próximas aplicações e contagens.

    O escopo segue o perfil (turmas do professor; escola/rede dos gestores e leitores).
    """
    cscope = await get_effective_classroom_scope(db, ctx)
    classroom_ids = cscope.get("effective_classroom_ids")

    vazio = {
        "pendencias": {
            "sem_presenca": {"total": 0, "items": []},
            "sem_respostas": {"total": 0, "items": []},
        },
        "proximas": [],
    }
    if classroom_ids is not None and len(classroom_ids) == 0:
        return vazio

    if classroom_ids is None:
        cfilter = ""
        params: dict = {}
    else:
        cfilter = "AND sch.classroom_id = ANY(CAST(:cids AS uuid[]))"
        params = {"cids": [str(x) for x in classroom_ids]}

    select_cols = """
        SELECT sch.id AS schedule_id,
               sch.start_time, sch.end_time,
               sch.classroom_id,
               a.macro_assessment_id,
               a.title AS assessment_title,
               c.name AS classroom_name,
               s.name AS school_name,
               COUNT(*) OVER() AS total
        FROM assessment_schedules sch
        JOIN classrooms c ON c.id = sch.classroom_id
        JOIN assessments a ON a.id = sch.assessment_id
        LEFT JOIN schools s ON s.id = c.school_id
    """

    # 1) Agendamentos já encerrados sem presença efetivamente registrada.
    #    A lista pode já existir só com o status inicial ('registered'); a pendência é quando
    #    ninguém foi marcado como presente/ausente/saiu (nenhum status resolvido).
    sem_presenca = await fetch_all(
        db,
        f"""
        {select_cols}
        WHERE sch.end_time < now()
          AND NOT EXISTS (
            SELECT 1 FROM assessment_attendance_list al
            WHERE al.assessment_schedules_id = sch.id
              AND al.status IN ('present', 'absent', 'out')
          )
          {cfilter}
        ORDER BY sch.end_time DESC
        LIMIT 6
        """,
        params,
    )

    # 2) Aplicações abertas (janela corrente) ainda sem nenhuma resposta.
    sem_respostas = await fetch_all(
        db,
        f"""
        {select_cols}
        WHERE now() BETWEEN sch.start_time AND sch.end_time
          AND NOT EXISTS (
            SELECT 1 FROM question_student_responsed r WHERE r.schedule_id = sch.id
          )
          {cfilter}
        ORDER BY sch.end_time ASC
        LIMIT 6
        """,
        params,
    )

    # 3) Próximas aplicações (14 dias).
    proximas = await fetch_all(
        db,
        f"""
        {select_cols}
        WHERE sch.start_time BETWEEN now() AND now() + interval '14 days'
          {cfilter}
        ORDER BY sch.start_time ASC
        LIMIT 6
        """,
        params,
    )

    return {
        "pendencias": {
            "sem_presenca": {
                "total": int(sem_presenca[0]["total"]) if sem_presenca else 0,
                "items": [_schedule_item(r) for r in sem_presenca],
            },
            "sem_respostas": {
                "total": int(sem_respostas[0]["total"]) if sem_respostas else 0,
                "items": [_schedule_item(r) for r in sem_respostas],
            },
        },
        "proximas": [_schedule_item(r) for r in proximas],
    }


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
