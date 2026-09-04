"""Schemas de navegação e RBAC."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


AccessLevel = Literal["NONE", "VIEW", "EDIT", "MANAGE"]

ALLOWED_ICON_KEYS = frozenset({
    "bar-chart-box", "book-open", "building", "calendar", "calendar-event",
    "checkbox-circle", "dashboard", "file-chart", "file-list", "group",
    "robot", "school", "settings", "stack", "upload-cloud", "user-shared", "user-star",
})

CODE_PATTERN = r"^[a-z][a-z0-9_.]*$"


class NavigationModuleOutV1(BaseModel):
    code: str
    name: str
    route_path: str
    icon_key: str | None = None
    access_level: AccessLevel
    sort_order: int
    match_prefix: bool = True


class NavigationGroupOutV1(BaseModel):
    code: str
    name: str
    sort_order: int
    items: list[NavigationModuleOutV1]


class UserNavigationOutV1(BaseModel):
    version: str
    effective_role_code: str | None = None
    groups: list[NavigationGroupOutV1]
    modules: list[NavigationModuleOutV1] = Field(default_factory=list)


class RoleDefinitionOutV1(BaseModel):
    id: UUID
    code: str
    name: str
    description: str | None = None
    scope_type: str
    is_system: bool
    is_active: bool
    sort_order: int
    aliases: list[str] = Field(default_factory=list)


SCOPE_TYPES = frozenset({"platform", "school", "classroom", "self"})


class RoleDefinitionCreateV1(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    scope_type: str = Field(default="platform")
    sort_order: int | None = None
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        import re

        code = v.strip().lower().replace("-", "_")
        if not re.match(CODE_PATTERN, code):
            raise ValueError("code deve ser lowercase, começar com letra e usar a-z0-9_.")
        return code

    @field_validator("scope_type")
    @classmethod
    def validate_scope(cls, v: str) -> str:
        if v not in SCOPE_TYPES:
            raise ValueError("scope_type inválido")
        return v


class RoleDefinitionUpdateV1(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    scope_type: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None

    @field_validator("scope_type")
    @classmethod
    def validate_scope_update(cls, v: str | None) -> str | None:
        if v is not None and v not in SCOPE_TYPES:
            raise ValueError("scope_type inválido")
        return v


class NavigationGroupAdminOutV1(BaseModel):
    id: UUID
    code: str
    name: str
    description: str | None = None
    icon_key: str | None = None
    sort_order: int
    is_active: bool
    module_count: int = 0


class NavigationModuleAdminOutV1(BaseModel):
    id: UUID
    group_id: UUID
    group_code: str | None = None
    group_name: str | None = None
    code: str
    name: str
    description: str | None = None
    route_path: str
    icon_key: str | None = None
    sort_order: int
    is_active: bool
    match_prefix: bool = True
    required_feature_flag: str | None = None


class NavigationGroupCreateV1(BaseModel):
    code: str = Field(min_length=2, max_length=64, pattern=CODE_PATTERN)
    name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    icon_key: str | None = None
    sort_order: int | None = None
    is_active: bool = True

    @field_validator("code", mode="before")
    @classmethod
    def lower_code(cls, v: object) -> object:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("icon_key")
    @classmethod
    def validate_icon(cls, v: str | None) -> str | None:
        if v is not None and v not in ALLOWED_ICON_KEYS:
            raise ValueError("icon_key não permitido")
        return v


class NavigationGroupUpdateV1(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    icon_key: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None

    @field_validator("icon_key")
    @classmethod
    def validate_icon(cls, v: str | None) -> str | None:
        if v is not None and v not in ALLOWED_ICON_KEYS:
            raise ValueError("icon_key não permitido")
        return v


class NavigationModuleCreateV1(BaseModel):
    group_id: UUID
    code: str = Field(min_length=2, max_length=128, pattern=CODE_PATTERN)
    name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    route_path: str = Field(min_length=1, max_length=512)
    icon_key: str | None = None
    sort_order: int | None = None
    is_active: bool = True
    match_prefix: bool = True
    required_feature_flag: str | None = Field(default=None, max_length=64)

    @field_validator("code", mode="before")
    @classmethod
    def lower_code(cls, v: object) -> object:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("route_path")
    @classmethod
    def validate_route(cls, v: str) -> str:
        path = v.strip()
        if not path.startswith("/"):
            raise ValueError("route_path deve começar com /")
        if "://" in path or path.lower().startswith("javascript:"):
            raise ValueError("route_path inválido")
        return path

    @field_validator("icon_key")
    @classmethod
    def validate_icon(cls, v: str | None) -> str | None:
        if v is not None and v not in ALLOWED_ICON_KEYS:
            raise ValueError("icon_key não permitido")
        return v


class NavigationModuleUpdateV1(BaseModel):
    group_id: UUID | None = None
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    route_path: str | None = Field(default=None, min_length=1, max_length=512)
    icon_key: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None
    match_prefix: bool | None = None
    required_feature_flag: str | None = Field(default=None, max_length=64)

    @field_validator("route_path")
    @classmethod
    def validate_route_update(cls, v: str | None) -> str | None:
        if v is None:
            return v
        path = v.strip()
        if not path.startswith("/"):
            raise ValueError("route_path deve começar com /")
        if "://" in path:
            raise ValueError("route_path inválido")
        return path

    @field_validator("icon_key")
    @classmethod
    def validate_icon_update(cls, v: str | None) -> str | None:
        if v is not None and v not in ALLOWED_ICON_KEYS:
            raise ValueError("icon_key não permitido")
        return v


class AccessMatrixEntryV1(BaseModel):
    role_definition_id: UUID
    navigation_module_id: UUID
    access_level: AccessLevel


class AccessMatrixRoleOutV1(BaseModel):
    id: UUID
    code: str
    name: str
    sort_order: int
    is_active: bool = True


class AccessMatrixModuleOutV1(BaseModel):
    id: UUID
    code: str
    name: str
    group_id: UUID
    group_code: str
    group_name: str
    group_sort_order: int
    sort_order: int
    is_active: bool = True


class AccessMatrixOutV1(BaseModel):
    roles: list[AccessMatrixRoleOutV1]
    modules: list[AccessMatrixModuleOutV1]
    access: list[AccessMatrixEntryV1]


class AccessMatrixUpdateV1(BaseModel):
    updates: list[AccessMatrixEntryV1]

