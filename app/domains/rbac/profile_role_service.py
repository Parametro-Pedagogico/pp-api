"""Resolução de papel legado (enum) × catálogo role_definitions ao criar/atualizar profiles."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.rbac import role_repository as repo

SCOPE_TO_USER_ROLE: dict[str, str] = {
    "self": "STUDENT",
    "classroom": "TEACHER",
    "school": "SCHOOL_ADMIN",
    "platform": "PLATFORM_ADMIN",
}

_CORE_ENUM_TO_CODE = {
    "STUDENT": "student",
    "TEACHER": "teacher",
    "SCHOOL_ADMIN": "school_admin",
    "PLATFORM_ADMIN": "platform_admin",
}


def _normalize_legacy_role(role: str) -> str:
    r = str(role).strip().upper().replace("-", "_")
    if r in ("ALUNO", "ESTUDANTE"):
        return "STUDENT"
    if r == "PROFESSOR":
        return "TEACHER"
    return r


async def resolve_profile_role_assignment(
    db: AsyncSession,
    *,
    role_definition_id: UUID | None = None,
    legacy_role: str | None = None,
) -> tuple[str, UUID | None]:
    """
    Retorna (valor enum user_role, role_definition_id).
    Preferir role_definition_id quando informado.
    """
    if role_definition_id is not None:
        rd = await repo.get_role_definition(db, role_definition_id)
        if not rd:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Perfil inválido")
        if not bool(rd.get("is_active")):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Perfil inativo")
        scope = str(rd.get("scope_type") or "")
        enum_role = SCOPE_TO_USER_ROLE.get(scope)
        if not enum_role:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Escopo de perfil não suportado: {scope}",
            )
        return enum_role, role_definition_id

    if legacy_role:
        normalized = _normalize_legacy_role(legacy_role)
        rd = await repo.resolve_role_definition(db, legacy_role)
        rd_id = UUID(str(rd["id"])) if rd else None
        if rd_id and str(rd.get("scope_type") or "") in SCOPE_TO_USER_ROLE:
            return SCOPE_TO_USER_ROLE[str(rd["scope_type"])], rd_id
        allowed = set(SCOPE_TO_USER_ROLE.values())
        if normalized not in allowed:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Papel inválido: {legacy_role!r}. Use role_definition_id para perfis customizados.",
            )
        if rd_id is None and normalized in _CORE_ENUM_TO_CODE:
            core = await repo.get_role_definition_by_code(db, _CORE_ENUM_TO_CODE[normalized])
            if core:
                rd_id = UUID(str(core["id"]))
        return normalized, rd_id

    raise HTTPException(status.HTTP_400_BAD_REQUEST, "role ou role_definition_id é obrigatório")
