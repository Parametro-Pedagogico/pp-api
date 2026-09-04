from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SchoolAuthProviderItemV1(BaseModel):
    auth_provider_id: UUID
    code: str
    name: str
    provider_type: str
    is_active: bool
    has_local_row: bool
    source: Literal["local", "inherited", "inactive"]


class SchoolAuthInheritedFromV1(BaseModel):
    school_id: UUID
    display_name: str


class SchoolAuthConfigOutV1(BaseModel):
    school_id: UUID
    school_name: str
    parent_id: UUID | None = None
    parent_name: str | None = None
    auth_inherit_from_parent: bool
    inherited_from: SchoolAuthInheritedFromV1 | None = None
    effective_methods: list[Literal["password", "google", "microsoft"]]
    providers: list[SchoolAuthProviderItemV1]


class SchoolAuthConfigUpdateV1(BaseModel):
    auth_inherit_from_parent: bool = False
    active_provider_ids: list[UUID] = Field(default_factory=list)
