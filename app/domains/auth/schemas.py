from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class FirebaseExchangeRequest(BaseModel):
    id_token: str = Field(..., min_length=10)

    @model_validator(mode="before")
    @classmethod
    def accept_camel_case_payload(cls, data: object) -> object:
        if isinstance(data, dict) and "id_token" not in data and "idToken" in data:
            data = dict(data)
            data["id_token"] = data.get("idToken")
        return data

    @field_validator("id_token", mode="before")
    @classmethod
    def strip_id_token(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v


class ProfileOut(BaseModel):
    id: UUID
    full_name: str | None = None
    email: str | None = None
    role: str
    school_id: UUID | None = None
    person_id: UUID | None = None
    code: str | None = None
    metadata: dict[str, Any] | list[Any] | str | None = None
    # (Fase 2) Dão ao frontend o papel e o escopo sem adivinhar por grafia:
    role_definition_code: str | None = None  # código canônico do papel (ex.: "diretor", "coordenador")
    scope_type: str | None = None  # platform | school | classroom | self
    school_type: str | None = None  # tipo do nó de escopo: unidade, rede ou secretaria
    school_name: str | None = None  # nome do nó de escopo

    @classmethod
    def from_row(cls, prof: dict[str, Any]) -> "ProfileOut":
        """Monta a partir de uma linha de `vw_profiles` enriquecida (ver repository.py)."""
        return cls(
            id=prof["id"],
            full_name=prof.get("full_name"),
            email=prof.get("email"),
            role=str(prof["role"]),
            school_id=prof.get("school_id"),
            person_id=prof.get("person_id"),
            code=prof.get("code"),
            metadata=prof.get("metadata"),
            role_definition_code=prof.get("role_definition_code"),
            scope_type=prof.get("scope_type"),
            school_type=prof.get("school_type"),
            school_name=prof.get("school_name"),
        )


class FirebaseExchangeResponse(BaseModel):
    person_id: UUID
    profiles: list[ProfileOut]


class SelectProfileRequest(BaseModel):
    profile_id: UUID
    id_token: str = Field(
        ...,
        min_length=10,
        description="Firebase ID token para provar identidade antes de existir access token da API.",
    )

    @model_validator(mode="before")
    @classmethod
    def accept_camel_case_payload(cls, data: object) -> object:
        if isinstance(data, dict) and "id_token" not in data and "idToken" in data:
            data = dict(data)
            data["id_token"] = data.get("idToken")
        return data

    @field_validator("id_token", mode="before")
    @classmethod
    def strip_id_token_select(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v


class AuthSessionRequest(BaseModel):
    """Um único passo: Firebase + perfil ativo + criação de `app_sessions` e tokens."""

    id_token: str = Field(..., min_length=10)
    profile_id: UUID

    @model_validator(mode="before")
    @classmethod
    def accept_camel_case_payload(cls, data: object) -> object:
        if isinstance(data, dict) and "id_token" not in data and "idToken" in data:
            data = dict(data)
            data["id_token"] = data.get("idToken")
        return data

    @field_validator("id_token", mode="before")
    @classmethod
    def strip_id_token_session(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v


class SessionOut(BaseModel):
    id: UUID
    expires_at: datetime


class AuthSessionResponse(BaseModel):
    person_id: UUID
    profiles: list[ProfileOut]
    active_profile: ProfileOut
    session: SessionOut
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=10)


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None)
