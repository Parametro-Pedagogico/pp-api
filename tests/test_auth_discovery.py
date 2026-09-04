"""Testes de descoberta de autenticação."""

import hashlib
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.domains.auth import discovery as disc
from app.core.security import create_discovery_challenge_token


def test_normalize_email():
    assert disc.normalize_email("  User@School.COM ") == "user@school.com"


def test_validate_email_syntax_rejects_invalid():
    with pytest.raises(HTTPException) as exc:
        disc.validate_email_syntax("not-an-email")
    assert exc.value.status_code == 422


def test_email_hash_deterministic():
    h1 = disc.email_hash("a@b.com")
    h2 = disc.email_hash("a@b.com")
    assert h1 == h2
    assert h1 == hashlib.sha256(b"a@b.com").hexdigest()


def test_decoy_response_shape():
    out = disc._decoy_response("unknown@x.com")
    assert out["method"] == "password"
    assert out["challenge_id"]
    assert out["institution"] is None


def test_validate_discovery_challenge_decoy_fails():
    token = create_discovery_challenge_token(
        email_hash=disc.email_hash("x@y.com"), method="password", decoy=True
    )
    with pytest.raises(HTTPException) as exc:
        disc.validate_discovery_challenge(token)
    assert exc.value.status_code == 401


def test_validate_discovery_challenge_replay():
    token = create_discovery_challenge_token(
        email_hash=disc.email_hash("x@y.com"), method="password", decoy=False
    )
    disc.validate_discovery_challenge(token)
    with pytest.raises(HTTPException) as exc:
        disc.validate_discovery_challenge(token)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_discover_unknown_email_returns_decoy(monkeypatch):
    async def fake_fetch(_db, _email):
        return None

    async def noop_delay():
        return None

    monkeypatch.setattr(disc, "fetch_person_by_email", fake_fetch)
    monkeypatch.setattr(disc, "_uniform_delay", noop_delay)
    monkeypatch.setattr(disc, "check_rate_limit", lambda **_: True)

    out = await disc.discover_auth_method(object(), email="nobody@school.com", ip="127.0.0.1")
    assert out["method"] == "password"
    assert out["challenge_id"]


@pytest.mark.asyncio
async def test_discover_single_school_password(monkeypatch):
    person_id = uuid4()
    school_id = uuid4()

    async def fake_fetch(_db, _email):
        return {"id": str(person_id), "can_login": True, "status": "published"}

    async def fake_profiles(_db, _pid):
        return [{"id": str(uuid4()), "school_id": str(school_id), "role": "teacher"}]

    async def fake_bundle(_db, sid):
        return {
            "school_id": sid,
            "display_name": "Escola Horizonte",
            "methods": ["password"],
            "primary_method": "password",
        }

    async def noop_delay():
        return None

    monkeypatch.setattr(disc, "fetch_person_by_email", fake_fetch)
    monkeypatch.setattr(disc, "fetch_login_profiles", fake_profiles)
    monkeypatch.setattr(disc, "_bundle_school_auth", fake_bundle)
    monkeypatch.setattr(disc, "_uniform_delay", noop_delay)
    monkeypatch.setattr(disc, "check_rate_limit", lambda **_: True)

    out = await disc.discover_auth_method(object(), email="t@horizonte.com", ip="127.0.0.1")
    assert out["method"] == "password"
    assert out["institution"]["display_name"] == "Escola Horizonte"


@pytest.mark.asyncio
async def test_rate_limit_blocks(monkeypatch):
    monkeypatch.setattr(disc, "check_rate_limit", lambda **_: False)
    with pytest.raises(HTTPException) as exc:
        await disc.discover_auth_method(object(), email="a@b.com", ip="1.2.3.4")
    assert exc.value.status_code == 429
