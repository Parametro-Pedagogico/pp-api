"""Testes de enforcement de acesso por módulo."""

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.domains.rbac import module_access_service as svc


@pytest.mark.asyncio
async def test_assert_module_access_allows_manage(monkeypatch):
    from app.core.deps import AuthContext

    ctx = AuthContext(
        session_id=uuid4(),
        person_id=uuid4(),
        active_profile_id=uuid4(),
        role="questions_editor",
        school_id=None,
    )

    async def fake_level(_db, _ctx, _code):
        return "MANAGE"

    monkeypatch.setattr(svc, "get_module_access_level", fake_level)

    await svc.assert_module_access(object(), ctx, "admin.questions", "VIEW")


@pytest.mark.asyncio
async def test_assert_module_access_denies_view(monkeypatch):
    from app.core.deps import AuthContext

    ctx = AuthContext(
        session_id=uuid4(),
        person_id=uuid4(),
        active_profile_id=uuid4(),
        role="questions_editor",
        school_id=None,
    )

    async def fake_level(_db, _ctx, _code):
        return "NONE"

    monkeypatch.setattr(svc, "get_module_access_level", fake_level)

    with pytest.raises(HTTPException) as exc:
        await svc.assert_module_access(object(), ctx, "admin.questions", "VIEW")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_legacy_admin_bypasses_matrix(monkeypatch):
    from app.core.deps import AuthContext

    ctx = AuthContext(
        session_id=uuid4(),
        person_id=uuid4(),
        active_profile_id=uuid4(),
        role="platform_admin",
        school_id=None,
    )

    level = await svc.get_module_access_level(object(), ctx, "admin.questions")
    assert level == "MANAGE"
