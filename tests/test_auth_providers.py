"""Testes admin auth providers (autorização e validação)."""

import pytest
from fastapi import HTTPException

from app.v1.auth_providers_router import _assert_platform_admin, _serialize_provider
from app.core.deps import AuthContext
from uuid import uuid4


def _ctx(role: str) -> AuthContext:
    return AuthContext(
        person_id=uuid4(),
        active_profile_id=uuid4(),
        session_id=uuid4(),
        role=role,
        school_id=None,
    )


def test_assert_platform_admin_allows():
    _assert_platform_admin(_ctx("platform_admin"))


def test_assert_platform_admin_denies_teacher():
    with pytest.raises(HTTPException) as exc:
        _assert_platform_admin(_ctx("teacher"))
    assert exc.value.status_code == 403


def test_serialize_provider():
    row = {
        "id": str(uuid4()),
        "code": "password",
        "name": "Senha",
        "provider_type": "PASSWORD",
        "firebase_provider_id": "password",
        "is_active": True,
        "school_count": 3,
        "created_at": "2026-01-01",
        "updated_at": "2026-01-01",
    }
    out = _serialize_provider(row)
    assert out.code == "password"
    assert out.school_count == 3
