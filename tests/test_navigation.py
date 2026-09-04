"""Testes de navegação dinâmica e catálogo de papéis."""

from uuid import uuid4

import pytest

from app.domains.navigation import service as nav_svc
from app.domains.rbac import role_repository as role_repo


@pytest.mark.asyncio
async def test_resolve_role_definition_by_alias(monkeypatch):
    calls: list[str] = []

    async def fake_fetch_one(_db, sql, params=None):
        if "role_definitions" in sql and "alias" not in sql.lower():
            calls.append("code")
            return None
        if "role_definition_aliases" in sql:
            calls.append("alias")
            return {
                "id": str(uuid4()),
                "code": "teacher",
                "name": "Professor",
                "scope_type": "classroom",
                "is_system": True,
                "is_active": True,
                "sort_order": 30,
            }
        return None

    monkeypatch.setattr(role_repo, "fetch_one", fake_fetch_one)

    row = await role_repo.resolve_role_definition(object(), "professor")
    assert row is not None
    assert row["code"] == "teacher"
    assert "alias" in calls


@pytest.mark.asyncio
async def test_resolve_navigation_role_code_school_view(monkeypatch):
    from app.core.deps import AuthContext

    ctx = AuthContext(
        session_id=uuid4(),
        person_id=uuid4(),
        active_profile_id=uuid4(),
        role="platform_admin",
        school_id=None,
    )
    school_view = uuid4()

    async def fake_get(_db, code):
        return {"code": "school_admin", "id": str(uuid4())}

    monkeypatch.setattr(role_repo, "get_role_definition_by_code", fake_get)

    code = await nav_svc.resolve_navigation_role_code(
        object(), ctx, school_view_id=school_view
    )
    assert code == "school_admin"


@pytest.mark.asyncio
async def test_feature_flag_assistant_requires_bot(monkeypatch):
    from app.core.deps import AuthContext

    ctx = AuthContext(
        session_id=uuid4(),
        person_id=uuid4(),
        active_profile_id=uuid4(),
        role="teacher",
        school_id=uuid4(),
    )

    async def fake_bot(_db, _sid):
        return False

    monkeypatch.setattr(nav_svc, "_school_bot_enabled", fake_bot)

    enabled = await nav_svc._feature_flag_enabled(
        object(), "assistant_school_bot", ctx=ctx, school_view_id=None
    )
    assert enabled is False


def test_is_platform_admin_role_legacy():
    assert nav_svc.is_platform_admin_role("coordenador_master")
    assert nav_svc.is_platform_admin_role("administrator")
    assert not nav_svc.is_platform_admin_role("teacher")


@pytest.mark.asyncio
async def test_delete_navigation_group_rejects_when_modules_exist(monkeypatch):
    from app.domains.navigation import admin_service as admin_svc
    from app.core.deps import AuthContext

    group_id = uuid4()
    ctx = AuthContext(
        session_id=uuid4(),
        person_id=uuid4(),
        active_profile_id=uuid4(),
        role="platform_admin",
        school_id=None,
    )

    async def fake_get_group(_db, _gid):
        return {"id": str(group_id), "code": "test", "name": "Test"}

    async def fake_count(_db, _gid):
        return 2

    monkeypatch.setattr(admin_svc.repo, "get_navigation_group", fake_get_group)
    monkeypatch.setattr(admin_svc.repo, "count_modules_in_group", fake_count)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await admin_svc.delete_group(object(), group_id, ctx)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_delete_navigation_group_ok_when_empty(monkeypatch):
    from app.domains.navigation import admin_service as admin_svc
    from app.core.deps import AuthContext

    group_id = uuid4()
    ctx = AuthContext(
        session_id=uuid4(),
        person_id=uuid4(),
        active_profile_id=uuid4(),
        role="platform_admin",
        school_id=None,
    )
    deleted: list[str] = []

    async def fake_get_group(_db, _gid):
        return {"id": str(group_id), "code": "test", "name": "Test"}

    async def fake_count(_db, _gid):
        return 0

    async def fake_delete(_db, gid):
        deleted.append(str(gid))

    async def fake_audit(*_a, **_k):
        return None

    async def fake_commit(_db):
        return None

    monkeypatch.setattr(admin_svc.repo, "get_navigation_group", fake_get_group)
    monkeypatch.setattr(admin_svc.repo, "count_modules_in_group", fake_count)
    monkeypatch.setattr(admin_svc.repo, "delete_navigation_group", fake_delete)
    monkeypatch.setattr(admin_svc.repo, "insert_navigation_audit", fake_audit)

    class FakeDb:
        async def commit(self):
            return None

    await admin_svc.delete_group(FakeDb(), group_id, ctx)
    assert deleted == [str(group_id)]
