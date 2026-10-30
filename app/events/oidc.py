"""Validação do token OIDC que o Pub/Sub envia no push (segurança do endpoint de resultado).

O Pub/Sub, numa assinatura push com service account, manda `Authorization: Bearer <JWT>` assinado
pelo Google, com `aud` = a audiência configurada e `email` = a service account do push. Aqui o token
é verificado contra as chaves públicas do Google (JWKS).

Quando `settings.pubsub_push_audience` está vazia, a validação fica **desligada** (dev/local). Em
produção, defina a audiência (e, idealmente, a service account) para o endpoint só aceitar a assinatura.
"""

from __future__ import annotations

import jwt
from fastapi import HTTPException, Request, status
from jwt import PyJWKClient

from app.core.config import settings

_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}

_jwk_client: PyJWKClient | None = None


def _client() -> PyJWKClient:
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = PyJWKClient(_CERTS_URL)
    return _jwk_client


async def verify_pubsub_push(request: Request) -> None:
    """Dependência FastAPI: valida o OIDC do push. Levanta 401 se inválido.

    Desligada quando `pubsub_push_audience` não está configurada.
    """
    audience = (settings.pubsub_push_audience or "").strip()
    if not audience:
        return  # dev/local: validação desligada (produção deve configurar a audiência).

    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "push sem token OIDC")
    token = auth.split(" ", 1)[1]
    try:
        signing_key = _client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token, signing_key.key, algorithms=["RS256"], audience=audience
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"OIDC inválido: {e}") from e

    if claims.get("iss") not in _ISSUERS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "emissor OIDC inesperado")

    expected_sa = (settings.pubsub_push_service_account or "").strip()
    if expected_sa:
        if claims.get("email") != expected_sa:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "service account OIDC inesperada"
            )
        if not claims.get("email_verified", False):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "e-mail da service account não verificado"
            )
