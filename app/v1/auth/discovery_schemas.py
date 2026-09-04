from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class DiscoveryRequestV1(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)

    @field_validator("email", mode="before")
    @classmethod
    def strip_email(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v


class InstitutionDisplayV1(BaseModel):
    display_name: str


class InstitutionChoiceV1(BaseModel):
    choice_id: str
    display_name: str


class DiscoveryResponseV1(BaseModel):
    challenge_id: str
    method: Literal["password", "google", "microsoft"] | None = None
    methods: list[Literal["password", "google", "microsoft"]] | None = None
    institution: InstitutionDisplayV1 | None = None
    institutions: list[InstitutionChoiceV1] | None = None
    message: str | None = None


class DiscoveryChooseRequestV1(BaseModel):
    challenge_id: str = Field(..., min_length=10)
    choice_id: str = Field(..., min_length=10)


class AuthProviderOutV1(BaseModel):
    id: UUID
    code: str
    name: str
    provider_type: str
    firebase_provider_id: str | None = None
    is_active: bool
    school_count: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


class AuthProviderCreateV1(BaseModel):
    code: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z0-9_]+$")
    name: str = Field(..., min_length=2, max_length=255)
    provider_type: Literal["PASSWORD", "GOOGLE", "MICROSOFT"]
    firebase_provider_id: str | None = Field(default=None, max_length=128)

    @field_validator("code", mode="before")
    @classmethod
    def lower_code(cls, v: object) -> object:
        return v.strip().lower() if isinstance(v, str) else v


class AuthProviderUpdateV1(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    firebase_provider_id: str | None = Field(default=None, max_length=128)
    is_active: bool | None = None


class SchoolAuthProviderOutV1(BaseModel):
    id: UUID
    school_id: UUID
    auth_provider_id: UUID
    is_active: bool
    is_default: bool
    provider_code: str | None = None
    provider_name: str | None = None
    provider_type: str | None = None


class SchoolAuthProviderUpsertV1(BaseModel):
    auth_provider_id: UUID
