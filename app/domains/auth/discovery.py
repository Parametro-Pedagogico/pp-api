"""Descoberta de método de autenticação institucional (anti-enumeração)."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from uuid import UUID

import jwt
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.discovery_rate_limit import check_rate_limit, mark_discovery_jti_used
from app.core.security import (
    DiscoveryMethod,
    create_discovery_challenge_token,
    create_discovery_choice_token,
    create_discovery_choose_token,
    decode_discovery_token,
)
from app.domains.auth import providers_repository as providers_repo
from app.domains.auth.school_auth_service import resolve_school_auth_methods
from app.v1._sql import fetch_all, fetch_one

_log = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_GENERIC_MESSAGE = (
    "Se existir uma conta com este e-mail, você verá as opções de acesso na próxima etapa."
)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def email_hash(normalized: str) -> str:
    return hashlib.sha256(normalized.encode()).hexdigest()


def validate_email_syntax(email: str) -> None:
    if not email or len(email) > 320 or not _EMAIL_RE.match(email):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Informe um e-mail válido.")


async def _uniform_delay() -> None:
    await asyncio.sleep(0.15)


async def fetch_person_by_email(db: AsyncSession, normalized_email: str) -> dict | None:
    return await fetch_one(
        db,
        """
        SELECT id, email, can_login, status
        FROM people
        WHERE lower(btrim(email)) = :email
        LIMIT 1
        """,
        {"email": normalized_email},
    )


async def fetch_login_profiles(db: AsyncSession, person_id: UUID) -> list[dict]:
    return await fetch_all(
        db,
        """
        SELECT id, school_id, role
        FROM vw_profiles
        WHERE person_id = CAST(:pid AS uuid)
          AND school_id IS NOT NULL
        ORDER BY created_at NULLS LAST
        """,
        {"pid": str(person_id)},
    )


async def _bundle_school_auth(db: AsyncSession, school_id: UUID) -> dict | None:
    rows = await resolve_school_auth_methods(db, school_id)
    if not rows:
        return None
    methods: list[DiscoveryMethod] = []
    seen: set[str] = set()
    for row in rows:
        method = row["method"]
        if method in seen:
            continue
        seen.add(method)
        methods.append(method)  # type: ignore[arg-type]
    if not methods:
        return None
    return {
        "school_id": school_id,
        "display_name": str(rows[0]["display_name"]),
        "methods": methods,
        "primary_method": methods[0],
    }


def _discovery_success_payload(
    *,
    email_hash: str,
    person_id: UUID,
    bundle: dict,
) -> dict:
    methods: list[DiscoveryMethod] = bundle["methods"]
    primary: DiscoveryMethod = bundle["primary_method"]
    school_id: UUID = bundle["school_id"]
    single_method = len(methods) == 1
    return {
        "challenge_id": create_discovery_challenge_token(
            email_hash=email_hash,
            method=primary,
            person_id=person_id,
            school_id=school_id,
        ),
        "method": primary if single_method else None,
        "methods": methods if not single_method else None,
        "institution": {"display_name": bundle["display_name"]},
        "institutions": None,
        "message": _GENERIC_MESSAGE,
    }


async def resolve_school_provider(db: AsyncSession, school_id: UUID) -> dict | None:
    """Compatibilidade: retorna o primeiro método da escola."""
    bundle = await _bundle_school_auth(db, school_id)
    if not bundle:
        return None
    primary = bundle["primary_method"]
    return {
        "school_id": school_id,
        "display_name": bundle["display_name"],
        "method": primary,
        "methods": bundle["methods"],
        "provider_type": providers_repo.METHOD_TO_PROVIDER_TYPE.get(primary, "PASSWORD"),
    }


def _decoy_response(normalized: str) -> dict:
    eh = email_hash(normalized)
    token = create_discovery_challenge_token(email_hash=eh, method="password", decoy=True)
    return {
        "challenge_id": token,
        "method": "password",
        "methods": None,
        "institution": None,
        "institutions": None,
        "message": _GENERIC_MESSAGE,
    }


async def discover_auth_method(
    db: AsyncSession,
    *,
    email: str,
    ip: str | None,
) -> dict:
    normalized = normalize_email(email)
    validate_email_syntax(normalized)

    if not check_rate_limit(ip=ip, email_normalized=normalized):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Muitas tentativas. Aguarde alguns minutos e tente novamente.",
        )

    await _uniform_delay()
    eh = email_hash(normalized)
    person = await fetch_person_by_email(db, normalized)

    if not person or not person.get("can_login") or str(person.get("status", "")).lower() == "archived":
        return _decoy_response(normalized)

    person_id = UUID(str(person["id"]))
    profiles = await fetch_login_profiles(db, person_id)
    if not profiles:
        return _decoy_response(normalized)

    school_ids = list(dict.fromkeys(UUID(str(p["school_id"])) for p in profiles if p.get("school_id")))
    resolved: list[dict] = []
    for sid in school_ids:
        bundle = await _bundle_school_auth(db, sid)
        if bundle:
            resolved.append(bundle)

    if not resolved:
        _log.warning("discovery_config_missing person_id=%s schools=%s", person_id, len(school_ids))
        return {
            "challenge_id": create_discovery_challenge_token(
                email_hash=eh, method="password", person_id=person_id, decoy=True
            ),
            "method": "password",
            "methods": None,
            "institution": None,
            "institutions": None,
            "message": (
                "Não foi possível identificar a forma de acesso da sua instituição. "
                "Entre em contato com o suporte."
            ),
        }

    if len(resolved) == 1:
        return _discovery_success_payload(email_hash=eh, person_id=person_id, bundle=resolved[0])

    parent_token = create_discovery_choose_token(email_hash=eh, person_id=person_id)
    parent = decode_discovery_token(parent_token)
    parent_jti = str(parent["jti"])
    institutions = []
    for bundle in resolved:
        primary: DiscoveryMethod = bundle["primary_method"]
        choice_token = create_discovery_choice_token(
            parent_jti=parent_jti,
            email_hash=eh,
            person_id=person_id,
            school_id=bundle["school_id"],
            method=primary,
        )
        institutions.append(
            {
                "choice_id": choice_token,
                "display_name": bundle["display_name"],
            }
        )

    return {
        "challenge_id": parent_token,
        "method": None,
        "methods": None,
        "institution": None,
        "institutions": institutions,
        "message": _GENERIC_MESSAGE,
    }


async def confirm_institution_choice(
    db: AsyncSession,
    *,
    challenge_id: str,
    choice_id: str,
    ip: str | None,
) -> dict:
    try:
        parent = decode_discovery_token(challenge_id)
        choice = decode_discovery_token(choice_id)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sessão de identificação expirada. Tente novamente.") from exc

    if parent.get("typ") != "discovery_choose" or choice.get("typ") != "discovery_choice":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sessão de identificação inválida.")

    if str(choice.get("par")) != str(parent.get("jti")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Seleção de instituição inválida.")

    if str(parent.get("sub")) != str(choice.get("sub")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Seleção de instituição inválida.")

    person_id = UUID(str(parent["pid"]))
    school_id = UUID(str(choice["sch"]))
    method: DiscoveryMethod = choice["meth"]  # type: ignore[assignment]
    eh = str(parent["sub"])

    if not check_rate_limit(ip=ip, email_normalized=eh):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Muitas tentativas. Aguarde e tente novamente.")

    await _uniform_delay()
    bundle = await _bundle_school_auth(db, school_id)
    if not bundle or method not in bundle["methods"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Configuração de acesso indisponível.")

    return _discovery_success_payload(email_hash=eh, person_id=person_id, bundle=bundle)


def validate_discovery_challenge(challenge_id: str, *, expected_method: DiscoveryMethod | None = None) -> dict:
    try:
        payload = decode_discovery_token(challenge_id)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sessão expirada. Volte e informe o e-mail novamente.") from exc

    typ = payload.get("typ")
    if typ not in ("discovery",):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Desafio inválido.")

    jti = str(payload.get("jti", ""))
    if not jti or not mark_discovery_jti_used(jti):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Desafio já utilizado ou expirado.")

    if payload.get("dec"):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Não foi possível entrar. Verifique e-mail e senha ou use a opção correta de acesso.",
        )

    method = payload.get("meth")
    if expected_method and method != expected_method:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Método de acesso incompatível.")

    return payload
