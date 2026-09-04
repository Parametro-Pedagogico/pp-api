"""Testes de configuração de autenticação por escola."""

import pytest
from fastapi import HTTPException
from uuid import uuid4

from app.domains.auth import providers_repository as repo
from app.domains.auth import school_auth_service as svc


@pytest.mark.asyncio
async def test_set_school_auth_config_requires_one_method(monkeypatch):
    school_id = uuid4()

    async def fake_get_school(_db, _sid):
        return {
            "id": str(school_id),
            "name": "Escola Teste",
            "parent": None,
            "auth_inherit_from_parent": False,
            "parent_name": None,
        }

    async def fake_catalog(_db, **kwargs):
        return [{"id": str(uuid4()), "code": "password", "name": "Senha", "provider_type": "PASSWORD", "is_active": True}]

    monkeypatch.setattr(svc, "_get_school_row", fake_get_school)
    monkeypatch.setattr(repo, "list_auth_providers", fake_catalog)

    with pytest.raises(HTTPException) as exc:
        await svc.set_school_auth_config(
            object(),
            school_id,
            auth_inherit_from_parent=False,
            active_provider_ids=[],
            actor_profile_id=None,
            actor_person_id=None,
        )
    assert exc.value.status_code == 422
