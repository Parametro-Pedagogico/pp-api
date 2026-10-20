"""Fase 2 — administração de usuários pelo técnico da secretaria (flag de contrato).

Cobre as guardas contra escalonamento: dentro da rede e sem atribuir/alterar papéis privilegiados.
"""

from uuid import UUID

import pytest
from fastapi import HTTPException

from app.core.deps import AuthContext
from app.v1 import directory_router as dr


def _ctx(role: str, school_id: UUID | None) -> AuthContext:
    return AuthContext(
        session_id="00000000-0000-0000-0000-000000000010",  # type: ignore[arg-type]
        person_id="00000000-0000-0000-0000-000000000011",  # type: ignore[arg-type]
        active_profile_id="00000000-0000-0000-0000-000000000012",  # type: ignore[arg-type]
        role=role,
        school_id=school_id,  # type: ignore[arg-type]
    )


def test_role_is_privileged():
    assert dr._role_is_privileged("PLATFORM_ADMIN")
    assert dr._role_is_privileged("school_admin")
    assert dr._role_is_privileged("diretor")
    assert dr._role_is_privileged(None, "admin")
    assert not dr._role_is_privileged("teacher", "student")
    assert not dr._role_is_privileged(None, None)


@pytest.mark.asyncio
async def test_tecnico_target_in_scope_ok(monkeypatch):
    rede = UUID("00000000-0000-0000-0000-0000000000a0")
    escola = UUID("00000000-0000-0000-0000-0000000000a1")

    async def fake_effective(_db, _ctx):
        return {"effective_school_ids": [rede, escola], "direct_school_id": rede, "is_admin_like": False}

    monkeypatch.setattr(dr, "get_effective_school_scope", fake_effective)
    ctx = _ctx("tecnico_secretaria", rede)
    # usuário da rede, papel não privilegiado → ok
    await dr._assert_tecnico_target_in_scope(
        object(), ctx, school_ids=[escola], privileged_values=("TEACHER",)
    )


@pytest.mark.asyncio
async def test_tecnico_target_fora_da_rede_403(monkeypatch):
    rede = UUID("00000000-0000-0000-0000-0000000000a0")
    outra = UUID("00000000-0000-0000-0000-0000000000ff")

    async def fake_effective(_db, _ctx):
        return {"effective_school_ids": [rede], "direct_school_id": rede, "is_admin_like": False}

    monkeypatch.setattr(dr, "get_effective_school_scope", fake_effective)
    ctx = _ctx("tecnico_secretaria", rede)
    with pytest.raises(HTTPException) as exc:
        await dr._assert_tecnico_target_in_scope(object(), ctx, school_ids=[outra])
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_tecnico_nao_atribui_papel_privilegiado(monkeypatch):
    rede = UUID("00000000-0000-0000-0000-0000000000a0")

    async def fake_effective(_db, _ctx):
        return {"effective_school_ids": [rede], "direct_school_id": rede, "is_admin_like": False}

    monkeypatch.setattr(dr, "get_effective_school_scope", fake_effective)
    ctx = _ctx("tecnico_secretaria", rede)
    with pytest.raises(HTTPException) as exc:
        await dr._assert_tecnico_target_in_scope(
            object(), ctx, school_ids=[rede], privileged_values=("SCHOOL_ADMIN",)
        )
    assert exc.value.status_code == 403
