"""Resolução de navegação dinâmica por perfil ativo."""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext
from app.domains.rbac import role_repository as roles_repo
from app.v1._scope import is_admin_like, is_teacher_like
from app.v1._sql import fetch_all, fetch_one


def _norm_role(role: str) -> str:
    return (role or "").strip().lower().replace("-", "_")


def is_platform_admin_role(role: str) -> bool:
    r = _norm_role(role)
    return r in (
        "platform_admin",
        "platformadmin",
        "plataform_admin",
        "admin",
        "administrator",
        "super_admin",
        "coordenador_master",
    ) or is_admin_like(role)


def is_school_admin_role(role: str) -> bool:
    r = _norm_role(role)
    return r in ("school_admin", "schooladmin")


async def resolve_navigation_role_code(
    db: AsyncSession,
    ctx: AuthContext,
    *,
    school_view_id: UUID | None,
) -> str | None:
    """Papel efetivo para montagem do menu."""
    if school_view_id and is_platform_admin_role(ctx.role):
        school_admin = await roles_repo.get_role_definition_by_code(db, "school_admin")
        return str(school_admin["code"]) if school_admin else "school_admin"
    row = await roles_repo.resolve_role_definition(db, ctx.role)
    return str(row["code"]) if row else None


async def _school_bot_enabled(db: AsyncSession, school_id: UUID | None) -> bool:
    if not school_id:
        return False
    row = await fetch_one(
        db,
        """
        SELECT bot_enabled FROM schools WHERE id = CAST(:id AS uuid)
        """,
        {"id": str(school_id)},
    )
    return bool(row and row.get("bot_enabled"))


async def _feature_flag_enabled(
    db: AsyncSession,
    flag: str | None,
    *,
    ctx: AuthContext,
    school_view_id: UUID | None,
) -> bool:
    if not flag:
        return True
    if flag == "assistant_school_bot":
        school_id = school_view_id or ctx.school_id
        if is_platform_admin_role(ctx.role) and not school_view_id:
            return True
        if is_teacher_like(ctx.role) or is_school_admin_role(ctx.role):
            return await _school_bot_enabled(db, school_id)
        return await _school_bot_enabled(db, school_id)
    return True


async def compute_navigation_version(db: AsyncSession) -> str:
    row = await fetch_one(
        db,
        """
        SELECT md5(
            coalesce(max(g.updated_at)::text, '') || '|' ||
            coalesce(max(m.updated_at)::text, '') || '|' ||
            coalesce(max(a.updated_at)::text, '') || '|' ||
            coalesce(max(r.updated_at)::text, '')
        ) AS v
        FROM navigation_groups g
        FULL OUTER JOIN navigation_modules m ON true
        FULL OUTER JOIN role_module_access a ON true
        FULL OUTER JOIN role_definitions r ON true
        """,
        {},
    )
    digest = str(row["v"]) if row and row.get("v") else "0"
    return hashlib.sha256(digest.encode()).hexdigest()[:16]


async def resolve_user_navigation(
    db: AsyncSession,
    ctx: AuthContext,
    *,
    school_view_id: UUID | None = None,
) -> dict[str, Any]:
    effective_code = await resolve_navigation_role_code(db, ctx, school_view_id=school_view_id)
    if not effective_code:
        return {
            "version": await compute_navigation_version(db),
            "effective_role_code": None,
            "groups": [],
            "modules": [],
        }

    role_row = await roles_repo.get_role_definition_by_code(db, effective_code)
    if not role_row:
        return {
            "version": await compute_navigation_version(db),
            "effective_role_code": effective_code,
            "groups": [],
            "modules": [],
        }

    rows = await fetch_all(
        db,
        """
        SELECT
            g.code AS group_code,
            g.name AS group_name,
            g.sort_order AS group_sort,
            m.code AS module_code,
            m.name AS module_name,
            m.route_path,
            m.icon_key,
            m.sort_order AS module_sort,
            m.match_prefix,
            m.required_feature_flag,
            rma.access_level
        FROM role_module_access rma
        JOIN navigation_modules m ON m.id = rma.navigation_module_id
        JOIN navigation_groups g ON g.id = m.group_id
        WHERE rma.role_definition_id = CAST(:role_id AS uuid)
          AND rma.is_active = true
          AND rma.access_level <> 'NONE'
          AND m.is_active = true
          AND g.is_active = true
        ORDER BY g.sort_order, g.code, m.sort_order, m.code
        """,
        {"role_id": str(role_row["id"])},
    )

    groups_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        flag = row.get("required_feature_flag")
        if not await _feature_flag_enabled(
            db, str(flag) if flag else None, ctx=ctx, school_view_id=school_view_id
        ):
            continue
        gcode = str(row["group_code"])
        if gcode not in groups_map:
            groups_map[gcode] = {
                "code": gcode,
                "name": str(row["group_name"]),
                "sort_order": int(row["group_sort"]),
                "items": [],
            }
        groups_map[gcode]["items"].append(
            {
                "code": str(row["module_code"]),
                "name": str(row["module_name"]),
                "route_path": str(row["route_path"]),
                "icon_key": row.get("icon_key"),
                "access_level": str(row["access_level"]),
                "sort_order": int(row["module_sort"]),
                "match_prefix": bool(row.get("match_prefix")),
            }
        )

    groups = sorted(groups_map.values(), key=lambda g: (g["sort_order"], g["code"]))

    all_rows = await fetch_all(
        db,
        """
        SELECT
            m.code AS module_code,
            m.name AS module_name,
            m.route_path,
            m.icon_key,
            m.sort_order AS module_sort,
            m.match_prefix,
            m.required_feature_flag,
            coalesce(rma.access_level, 'NONE') AS access_level
        FROM navigation_modules m
        JOIN navigation_groups g ON g.id = m.group_id
        LEFT JOIN role_module_access rma ON rma.navigation_module_id = m.id
            AND rma.role_definition_id = CAST(:role_id AS uuid)
            AND rma.is_active = true
        WHERE m.is_active = true
          AND g.is_active = true
        ORDER BY m.sort_order, m.code
        """,
        {"role_id": str(role_row["id"])},
    )

    modules_catalog: list[dict[str, Any]] = []
    for row in all_rows:
        flag = row.get("required_feature_flag")
        if not await _feature_flag_enabled(
            db, str(flag) if flag else None, ctx=ctx, school_view_id=school_view_id
        ):
            continue
        modules_catalog.append(
            {
                "code": str(row["module_code"]),
                "name": str(row["module_name"]),
                "route_path": str(row["route_path"]),
                "icon_key": row.get("icon_key"),
                "access_level": str(row["access_level"]),
                "sort_order": int(row["module_sort"]),
                "match_prefix": bool(row.get("match_prefix")),
            }
        )

    if is_platform_admin_role(ctx.role):
        for group in groups:
            for item in group["items"]:
                item["access_level"] = "MANAGE"
        for module in modules_catalog:
            module["access_level"] = "MANAGE"

    return {
        "version": await compute_navigation_version(db),
        "effective_role_code": effective_code,
        "groups": groups,
        "modules": modules_catalog,
    }
