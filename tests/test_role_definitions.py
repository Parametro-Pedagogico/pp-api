"""Testes de CRUD de role_definitions."""

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.domains.rbac import role_admin_service as svc
from app.domains.rbac import role_repository as role_repo
from app.v1.navigation_schemas import RoleDefinitionCreateV1, RoleDefinitionUpdateV1


def _ctx():
    from app.core.deps import AuthContext

    return AuthContext(
        session_id=uuid4(),
        person_id=uuid4(),
        active_profile_id=uuid4(),
        role="platform_admin",
        school_id=None,
    )


@pytest.mark.asyncio
async def test_create_role_duplicate_code(monkeypatch):
    async def fake_get_by_code(_db, code):
        return {"id": str(uuid4()), "code": code}

    monkeypatch.setattr(role_repo, "get_role_definition_by_code", fake_get_by_code)

    with pytest.raises(HTTPException) as exc:
        await svc.create_role(
            object(),
            RoleDefinitionCreateV1(code="coordinator", name="Coordenador", scope_type="school"),
            _ctx(),
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_update_core_role_cannot_deactivate(monkeypatch):
    role_id = uuid4()

    async def fake_get(_db, _id):
        return {
            "id": str(role_id),
            "code": "student",
            "name": "Aluno",
            "scope_type": "self",
            "is_system": True,
            "is_active": True,
            "sort_order": 40,
        }

    monkeypatch.setattr(role_repo, "get_role_definition", fake_get)

    with pytest.raises(HTTPException) as exc:
        await svc.update_role(
            object(),
            role_id,
            RoleDefinitionUpdateV1(is_active=False),
            _ctx(),
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_update_system_role_scope_blocked(monkeypatch):
    role_id = uuid4()

    async def fake_get(_db, _id):
        return {
            "id": str(role_id),
            "code": "teacher",
            "name": "Professor",
            "scope_type": "classroom",
            "is_system": True,
            "is_active": True,
            "sort_order": 30,
        }

    async def fake_update(*_a, **_k):
        raise AssertionError("update should not be called")

    async def fake_list_with_aliases(_db, **_k):
        return []

    monkeypatch.setattr(role_repo, "get_role_definition", fake_get)
    monkeypatch.setattr(role_repo, "update_role_definition", fake_update)
    monkeypatch.setattr(role_repo, "list_role_definitions_with_aliases", fake_list_with_aliases)

    with pytest.raises(HTTPException) as exc:
        await svc.update_role(
            object(),
            role_id,
            RoleDefinitionUpdateV1(scope_type="platform"),
            _ctx(),
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_delete_role_requires_inactive(monkeypatch):
    role_id = uuid4()

    async def fake_get(_db, _id):
        return {
            "id": str(role_id),
            "code": "coordinator",
            "name": "Coordenador",
            "scope_type": "school",
            "is_system": False,
            "is_active": True,
            "sort_order": 50,
        }

    monkeypatch.setattr(role_repo, "get_role_definition", fake_get)

    with pytest.raises(HTTPException) as exc:
        await svc.delete_role(object(), role_id, _ctx())
    assert exc.value.status_code == 409
    assert "Inative" in exc.value.detail


@pytest.mark.asyncio
async def test_delete_role_blocks_linked_profiles(monkeypatch):
    role_id = uuid4()

    async def fake_get(_db, _id):
        return {
            "id": str(role_id),
            "code": "coordinator",
            "name": "Coordenador",
            "scope_type": "school",
            "is_system": False,
            "is_active": False,
            "sort_order": 50,
        }

    async def fake_count(_db, _id, _code):
        return 2

    monkeypatch.setattr(role_repo, "get_role_definition", fake_get)
    monkeypatch.setattr(role_repo, "count_profiles_linked_to_role", fake_count)

    with pytest.raises(HTTPException) as exc:
        await svc.delete_role(object(), role_id, _ctx())
    assert exc.value.status_code == 409
    assert "2 usuário" in exc.value.detail


@pytest.mark.asyncio
async def test_delete_inactive_custom_role(monkeypatch):
    role_id = uuid4()
    deleted: list[UUID] = []

    async def fake_get(_db, _id):
        return {
            "id": str(role_id),
            "code": "coordinator",
            "name": "Coordenador",
            "scope_type": "school",
            "is_system": False,
            "is_active": False,
            "sort_order": 50,
        }

    async def fake_count(_db, _id, _code):
        return 0

    async def fake_delete(_db, rid):
        deleted.append(rid)

    async def fake_audit(*_a, **_k):
        return None

    monkeypatch.setattr(role_repo, "get_role_definition", fake_get)
    monkeypatch.setattr(role_repo, "count_profiles_linked_to_role", fake_count)
    monkeypatch.setattr(role_repo, "delete_role_definition", fake_delete)
    monkeypatch.setattr(svc, "insert_navigation_audit", fake_audit)

    class FakeDb:
        async def commit(self):
            return None

    await svc.delete_role(FakeDb(), role_id, _ctx())
    assert deleted == [role_id]


@pytest.mark.asyncio
async def test_delete_inactive_system_legacy_role(monkeypatch):
    role_id = uuid4()
    deleted: list[UUID] = []

    async def fake_get(_db, _id):
        return {
            "id": str(role_id),
            "code": "admin",
            "name": "Administrador (legacy)",
            "scope_type": "platform",
            "is_system": True,
            "is_active": False,
            "sort_order": 11,
        }

    async def fake_count(_db, _id, _code):
        return 0

    async def fake_delete(_db, rid):
        deleted.append(rid)

    async def fake_audit(*_a, **_k):
        return None

    monkeypatch.setattr(role_repo, "get_role_definition", fake_get)
    monkeypatch.setattr(role_repo, "count_profiles_linked_to_role", fake_count)
    monkeypatch.setattr(role_repo, "delete_role_definition", fake_delete)
    monkeypatch.setattr(svc, "insert_navigation_audit", fake_audit)

    class FakeDb:
        async def commit(self):
            return None

    await svc.delete_role(FakeDb(), role_id, _ctx())
    assert deleted == [role_id]


@pytest.mark.asyncio
async def test_delete_core_role_blocked(monkeypatch):
    role_id = uuid4()

    async def fake_get(_db, _id):
        return {
            "id": str(role_id),
            "code": "platform_admin",
            "name": "Administrador da plataforma",
            "scope_type": "platform",
            "is_system": True,
            "is_active": False,
            "sort_order": 10,
        }

    monkeypatch.setattr(role_repo, "get_role_definition", fake_get)

    with pytest.raises(HTTPException) as exc:
        await svc.delete_role(object(), role_id, _ctx())
    assert exc.value.status_code == 409
    assert "papel base" in exc.value.detail.lower()
