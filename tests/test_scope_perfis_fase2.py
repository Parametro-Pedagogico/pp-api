"""Fase 2 — escopo dos novos perfis (coordenador, diretor, técnico, secretário).

Verifica os predicados de papel e que o teto de escopo (subárvore do nó do perfil) é aplicado:
- diretor é tratado como school_admin;
- coordenador/técnico/secretário leem com teto, sem serem admin global;
- um técnico/secretário pendurado no nó da rede enxerga a subárvore inteira.
"""

from uuid import UUID

import pytest
from fastapi import HTTPException

from app.core.deps import AuthContext
from app.v1 import _scope


def _ctx(role: str, school_id: UUID | None) -> AuthContext:
    return AuthContext(
        session_id="00000000-0000-0000-0000-000000000010",  # type: ignore[arg-type]
        person_id="00000000-0000-0000-0000-000000000011",  # type: ignore[arg-type]
        active_profile_id="00000000-0000-0000-0000-000000000012",  # type: ignore[arg-type]
        role=role,
        school_id=school_id,  # type: ignore[arg-type]
    )


def test_diretor_e_tratado_como_school_admin():
    assert _scope.is_school_admin_like("diretor")
    assert _scope.is_school_admin_like("DIRETOR")
    assert _scope.is_staff_admin_role("diretor")  # pode escrever no escopo, como o gestor
    assert not _scope.is_school_scoped_reader("diretor")


def test_leitores_com_teto_nao_sao_staff_admin():
    for role in ("coordenador", "tecnico_secretaria", "secretario"):
        assert _scope.is_school_scoped_reader(role)
        assert _scope.can_read_school_scope(role)
        # Não podem escrever no escopo (sem acesso às rotas de gestor/plataforma):
        assert not _scope.is_staff_admin_role(role)
        assert not _scope.is_admin_like(role)


def test_can_read_school_scope_abrange_staff_e_leitores():
    assert _scope.can_read_school_scope("school_admin")
    assert _scope.can_read_school_scope("platform_admin")
    assert _scope.can_read_school_scope("diretor")
    assert not _scope.can_read_school_scope("teacher")
    assert not _scope.can_read_school_scope("student")


@pytest.mark.asyncio
async def test_secretario_na_rede_enxerga_subarvore(monkeypatch):
    rede = UUID("00000000-0000-0000-0000-0000000000a0")
    escola1 = UUID("00000000-0000-0000-0000-0000000000a1")
    escola2 = UUID("00000000-0000-0000-0000-0000000000a2")

    async def fake_effective(_db, _ctx):
        return {
            "effective_school_ids": [rede, escola1, escola2],
            "direct_school_id": rede,
            "is_admin_like": False,
        }

    async def fake_desc(_db, sid):
        return [sid, escola1, escola2] if sid == rede else [sid]

    monkeypatch.setattr(_scope, "get_effective_school_scope", fake_effective)
    monkeypatch.setattr(_scope, "get_descendant_school_ids", fake_desc)

    ctx = _ctx("secretario", rede)
    out = await _scope.resolve_admin_dashboard_school_ids(object(), ctx, None)
    assert set(out) == {rede, escola1, escola2}


@pytest.mark.asyncio
async def test_diretor_na_unidade_so_a_propria_escola(monkeypatch):
    escola = UUID("00000000-0000-0000-0000-0000000000b1")

    async def fake_effective(_db, _ctx):
        return {
            "effective_school_ids": [escola],
            "direct_school_id": escola,
            "is_admin_like": False,
        }

    async def fake_desc(_db, sid):
        return [sid]

    monkeypatch.setattr(_scope, "get_effective_school_scope", fake_effective)
    monkeypatch.setattr(_scope, "get_descendant_school_ids", fake_desc)

    ctx = _ctx("diretor", escola)
    out = await _scope.resolve_admin_dashboard_school_ids(object(), ctx, None)
    assert out == [escola]


@pytest.mark.asyncio
async def test_coordenador_sem_escola_recebe_403(monkeypatch):
    async def fake_effective(_db, _ctx):
        return {"effective_school_ids": [], "direct_school_id": None, "is_admin_like": False}

    monkeypatch.setattr(_scope, "get_effective_school_scope", fake_effective)
    ctx = _ctx("coordenador", None)
    with pytest.raises(HTTPException) as exc:
        await _scope.resolve_admin_dashboard_school_ids(object(), ctx, None)
    assert exc.value.status_code == 403


def test_presence_editor_roles():
    assert _scope.is_presence_editor_role("coordenador")
    assert _scope.is_presence_editor_role("tecnico_secretaria")
    assert _scope.is_presence_editor_role("tecnico-rede")
    # Secretário é só leitura; staff/professor tratados à parte no router.
    assert not _scope.is_presence_editor_role("secretario")
    assert not _scope.is_presence_editor_role("teacher")
    assert not _scope.is_presence_editor_role("school_admin")


def test_is_tecnico_secretaria_aceita_aliases():
    assert _scope.is_tecnico_secretaria("tecnico_secretaria")
    assert _scope.is_tecnico_secretaria("TECNICO_SECRETARIA")
    assert _scope.is_tecnico_secretaria("tecnico-rede")
    assert not _scope.is_tecnico_secretaria("secretario")
