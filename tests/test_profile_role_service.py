"""Testes de resolução de papel ao criar profiles."""

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.domains.rbac import profile_role_service as svc


@pytest.mark.asyncio
async def test_resolve_profile_role_from_definition_id(monkeypatch):
    role_id = uuid4()

    async def fake_get(_db, _rid):
        return {
            "id": str(role_id),
            "code": "questions_editor",
            "scope_type": "platform",
            "is_active": True,
        }

    monkeypatch.setattr(svc.repo, "get_role_definition", fake_get)

    enum_role, rd_id = await svc.resolve_profile_role_assignment(
        object(),
        role_definition_id=role_id,
    )
    assert enum_role == "PLATFORM_ADMIN"
    assert rd_id == role_id


@pytest.mark.asyncio
async def test_resolve_profile_role_rejects_inactive_definition(monkeypatch):
    role_id = uuid4()

    async def fake_get(_db, _rid):
        return {
            "id": str(role_id),
            "code": "questions_editor",
            "scope_type": "platform",
            "is_active": False,
        }

    monkeypatch.setattr(svc.repo, "get_role_definition", fake_get)

    with pytest.raises(HTTPException) as exc:
        await svc.resolve_profile_role_assignment(object(), role_definition_id=role_id)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_resolve_profile_role_rejects_unknown_custom_legacy(monkeypatch):
    async def fake_resolve(_db, _role):
        return None

    monkeypatch.setattr(svc.repo, "resolve_role_definition", fake_resolve)

    with pytest.raises(HTTPException) as exc:
        await svc.resolve_profile_role_assignment(object(), legacy_role="QUESTIONS_EDITOR")
    assert exc.value.status_code == 422
