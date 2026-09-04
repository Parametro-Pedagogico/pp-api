import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

import jwt

from app.core.config import settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_refresh_token(raw: str) -> str:
    payload = (settings.refresh_token_pepper + raw).encode()
    return hashlib.sha256(payload).hexdigest()


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def create_access_token(
    *,
    session_id: UUID,
    person_id: UUID,
    profile_id: UUID,
    role: str,
    school_id: UUID | None,
) -> str:
    now = _utcnow()
    exp = now + timedelta(minutes=settings.access_token_ttl_minutes)
    claims: dict[str, Any] = {
        "typ": "access",
        "sid": str(session_id),
        "sub": str(person_id),
        "prf": str(profile_id),
        "role": role,
        "sch": str(school_id) if school_id else None,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def create_bootstrap_token(*, person_id: UUID) -> str:
    """JWT curto pós-exchange; usado em POST /v1/auth/select-profile (sem reenviar Firebase ID token)."""
    now = _utcnow()
    exp = now + timedelta(minutes=settings.bootstrap_token_ttl_minutes)
    claims: dict[str, Any] = {
        "typ": "bootstrap",
        "sub": str(person_id),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_bootstrap_token(token: str) -> UUID:
    payload = jwt.decode(token.strip(), settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("typ") != "bootstrap":
        raise ValueError("Invalid bootstrap token type")
    return UUID(payload["sub"])


DiscoveryMethod = Literal["password", "google", "microsoft"]


def _discovery_exp() -> tuple[int, int]:
    now = _utcnow()
    exp = now + timedelta(minutes=settings.discovery_challenge_ttl_minutes)
    return int(now.timestamp()), int(exp.timestamp())


def create_discovery_challenge_token(
    *,
    email_hash: str,
    method: DiscoveryMethod,
    person_id: UUID | None = None,
    school_id: UUID | None = None,
    decoy: bool = False,
) -> str:
    """JWT opaco de curta duração para vincular e-mail normalizado ao método encontrado."""
    iat, exp = _discovery_exp()
    jti = secrets.token_urlsafe(16)
    claims: dict[str, Any] = {
        "typ": "discovery",
        "sub": email_hash,
        "meth": method,
        "jti": jti,
        "iat": iat,
        "exp": exp,
    }
    if person_id:
        claims["pid"] = str(person_id)
    if school_id:
        claims["sch"] = str(school_id)
    if decoy:
        claims["dec"] = True
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_discovery_choose_token(*, email_hash: str, person_id: UUID) -> str:
    iat, exp = _discovery_exp()
    jti = secrets.token_urlsafe(16)
    claims: dict[str, Any] = {
        "typ": "discovery_choose",
        "sub": email_hash,
        "pid": str(person_id),
        "jti": jti,
        "iat": iat,
        "exp": exp,
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_discovery_choice_token(
    *,
    parent_jti: str,
    email_hash: str,
    person_id: UUID,
    school_id: UUID,
    method: DiscoveryMethod,
) -> str:
    iat, exp = _discovery_exp()
    claims: dict[str, Any] = {
        "typ": "discovery_choice",
        "par": parent_jti,
        "sub": email_hash,
        "pid": str(person_id),
        "sch": str(school_id),
        "meth": method,
        "jti": secrets.token_urlsafe(16),
        "iat": iat,
        "exp": exp,
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_discovery_token(token: str) -> dict[str, Any]:
    return jwt.decode(token.strip(), settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def session_expires_at() -> datetime:
    return _utcnow() + timedelta(days=settings.refresh_token_ttl_days)
