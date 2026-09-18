"""CRUD de áreas curriculares e disciplinas + vínculos por série (grade)."""

from __future__ import annotations

import re
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.v1._catalog_order import curricular_area_label_order_sql, discipline_name_order_sql
from app.v1._scope import is_admin_like
from app.v1._sql import execute, fetch_all, fetch_one

router = APIRouter(tags=["v1-curricular-catalog"])


def _slugify(value: str) -> str:
    s = value.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "item"


def _assert_admin(ctx: AuthContext) -> None:
    if not is_admin_like(ctx.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas administradores")


class CurricularAreaOut(BaseModel):
    slug: str
    name: str
    official_name: str | None = None
    bncc_reference: str | None = None
    mec_reference: str | None = None
    description: str | None = None
    grade_ids: list[str] = Field(default_factory=list)


class CurricularAreaCreate(BaseModel):
    slug: str | None = Field(None, min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    official_name: str | None = None
    bncc_reference: str | None = None
    mec_reference: str | None = None
    description: str | None = None
    grade_ids: list[UUID] = Field(default_factory=list)


class CurricularAreaPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    official_name: str | None = None
    bncc_reference: str | None = None
    mec_reference: str | None = None
    description: str | None = None
    grade_ids: list[UUID] | None = None


class DisciplineOut(BaseModel):
    id: str
    name: str
    slug: str | None = None
    area_slug: str | None = None
    official_name: str | None = None
    bncc_component_code: str | None = None
    mec_reference: str | None = None
    description: str | None = None
    grade_ids: list[str] = Field(default_factory=list)


class DisciplineCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str | None = None
    area_slug: str | None = None
    official_name: str | None = None
    bncc_component_code: str | None = None
    mec_reference: str | None = None
    description: str | None = None
    grade_ids: list[UUID] = Field(default_factory=list)


class DisciplinePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    slug: str | None = None
    area_slug: str | None = None
    official_name: str | None = None
    bncc_component_code: str | None = None
    mec_reference: str | None = None
    description: str | None = None
    grade_ids: list[UUID] | None = None


async def _area_grade_ids(db: AsyncSession, slug: str) -> list[str]:
    rows = await fetch_all(
        db,
        "SELECT grade_id::text AS id FROM grade_curricular_areas WHERE area_slug = :slug",
        {"slug": slug},
    )
    return [str(r["id"]) for r in rows]


async def _discipline_grade_ids(db: AsyncSession, discipline_id: UUID) -> list[str]:
    rows = await fetch_all(
        db,
        """
        SELECT grade_id::text AS id FROM grade_disciplines
        WHERE discipline_id = CAST(:id AS uuid)
        """,
        {"id": str(discipline_id)},
    )
    return [str(r["id"]) for r in rows]


async def _sync_area_grades(db: AsyncSession, slug: str, grade_ids: list[UUID]) -> None:
    await execute(
        db,
        "DELETE FROM grade_curricular_areas WHERE area_slug = :slug",
        {"slug": slug},
    )
    for gid in grade_ids:
        await execute(
            db,
            """
            INSERT INTO grade_curricular_areas (grade_id, area_slug)
            VALUES (CAST(:gid AS uuid), :slug)
            ON CONFLICT DO NOTHING
            """,
            {"gid": str(gid), "slug": slug},
        )


async def _sync_discipline_grades(db: AsyncSession, discipline_id: UUID, grade_ids: list[UUID]) -> None:
    await execute(
        db,
        "DELETE FROM grade_disciplines WHERE discipline_id = CAST(:id AS uuid)",
        {"id": str(discipline_id)},
    )
    for gid in grade_ids:
        await execute(
            db,
            """
            INSERT INTO grade_disciplines (grade_id, discipline_id)
            VALUES (CAST(:gid AS uuid), CAST(:did AS uuid))
            ON CONFLICT DO NOTHING
            """,
            {"gid": str(gid), "did": str(discipline_id)},
        )


def _row_area(row: dict[str, Any], grade_ids: list[str]) -> dict[str, Any]:
    return {
        "slug": row["slug"],
        "name": row["name"],
        "official_name": row.get("official_name"),
        "bncc_reference": row.get("bncc_reference"),
        "mec_reference": row.get("mec_reference"),
        "description": row.get("description"),
        "grade_ids": grade_ids,
    }


def _row_discipline(row: dict[str, Any], grade_ids: list[str]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "slug": row.get("slug"),
        "area_slug": row.get("area_slug"),
        "official_name": row.get("official_name"),
        "bncc_component_code": row.get("bncc_component_code"),
        "mec_reference": row.get("mec_reference"),
        "description": row.get("description"),
        "grade_ids": grade_ids,
    }


@router.get("/curricular-areas")
async def list_curricular_areas_v1(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    grade_id: UUID | None = Query(None),
):
    area_order = curricular_area_label_order_sql("ca")
    if grade_id:
        rows = await fetch_all(
            db,
            f"""
            SELECT ca.*
            FROM curricular_areas ca
            JOIN grade_curricular_areas gca ON gca.area_slug = ca.slug
            WHERE gca.grade_id = CAST(:gid AS uuid)
            ORDER BY {area_order}
            """,
            {"gid": str(grade_id)},
        )
    else:
        rows = await fetch_all(
            db,
            f"SELECT * FROM curricular_areas ca ORDER BY {area_order}",
            {},
        )
    out = []
    for row in rows:
        gids = await _area_grade_ids(db, row["slug"])
        out.append(_row_area(row, gids))
    return {"items": out}


@router.post("/curricular-areas", status_code=status.HTTP_201_CREATED)
async def create_curricular_area_v1(
    body: CurricularAreaCreate,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    _assert_admin(ctx)
    slug = (body.slug or _slugify(body.name)).strip()
    existing = await fetch_one(
        db,
        "SELECT slug FROM curricular_areas WHERE slug = :slug",
        {"slug": slug},
    )
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Slug já existe")
    row = await fetch_one(
        db,
        """
        INSERT INTO curricular_areas (slug, name, official_name, bncc_reference, mec_reference, description)
        VALUES (:slug, :name, :official_name, :bncc_reference, :mec_reference, :description)
        RETURNING *
        """,
        {
            "slug": slug,
            "name": body.name.strip(),
            "official_name": body.official_name,
            "bncc_reference": body.bncc_reference,
            "mec_reference": body.mec_reference,
            "description": body.description,
        },
    )
    assert row
    await _sync_area_grades(db, slug, body.grade_ids)
    await db.commit()
    return _row_area(row, [str(g) for g in body.grade_ids])


@router.patch("/curricular-areas/{slug}")
async def patch_curricular_area_v1(
    slug: str,
    body: CurricularAreaPatch,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    _assert_admin(ctx)
    row = await fetch_one(
        db,
        "SELECT * FROM curricular_areas WHERE slug = :slug",
        {"slug": slug},
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Área não encontrada")
    sets: list[str] = []
    params: dict[str, Any] = {"slug": slug}
    for key, col in (
        ("name", "name"),
        ("official_name", "official_name"),
        ("bncc_reference", "bncc_reference"),
        ("mec_reference", "mec_reference"),
        ("description", "description"),
    ):
        val = getattr(body, key)
        if val is not None:
            sets.append(f"{col} = :{key}")
            params[key] = val.strip() if key == "name" and isinstance(val, str) else val
    if sets:
        row = await fetch_one(
            db,
            f"UPDATE curricular_areas SET {', '.join(sets)} WHERE slug = :slug RETURNING *",
            params,
        )
    if body.grade_ids is not None:
        await _sync_area_grades(db, slug, body.grade_ids)
    await db.commit()
    assert row
    gids = await _area_grade_ids(db, slug)
    return _row_area(row, gids)


@router.delete("/curricular-areas/{slug}")
async def delete_curricular_area_v1(
    slug: str,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    _assert_admin(ctx)
    in_use = await fetch_one(
        db,
        "SELECT 1 AS x FROM question_item WHERE area_slug = :slug LIMIT 1",
        {"slug": slug},
    )
    if in_use:
        raise HTTPException(status.HTTP_409_CONFLICT, "Área em uso em questões")
    await execute(db, "DELETE FROM curricular_areas WHERE slug = :slug", {"slug": slug})
    await db.commit()
    return {"ok": True}


@router.get("/disciplines")
async def list_disciplines_catalog_v1(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    grade_id: UUID | None = Query(None),
    area_slug: str | None = Query(None),
):
    where = ["1=1"]
    params: dict[str, Any] = {}
    if grade_id:
        where.append(
            "d.id IN (SELECT discipline_id FROM grade_disciplines WHERE grade_id = CAST(:gid AS uuid))"
        )
        params["gid"] = str(grade_id)
    if area_slug:
        where.append("d.area_slug = :area_slug")
        params["area_slug"] = area_slug
    disc_order = discipline_name_order_sql("d")
    rows = await fetch_all(
        db,
        f"SELECT d.* FROM disciplines d WHERE {' AND '.join(where)} ORDER BY {disc_order}",
        params,
    )
    out = []
    for row in rows:
        gids = await _discipline_grade_ids(db, row["id"])
        out.append(_row_discipline(row, gids))
    return {"items": out}


@router.post("/disciplines", status_code=status.HTTP_201_CREATED)
async def create_discipline_v1(
    body: DisciplineCreate,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    _assert_admin(ctx)
    if body.area_slug:
        area = await fetch_one(
            db,
            "SELECT slug FROM curricular_areas WHERE slug = :slug",
            {"slug": body.area_slug},
        )
        if not area:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Área inválida")
    slug = body.slug or _slugify(body.name)
    row = await fetch_one(
        db,
        """
        INSERT INTO disciplines (
          name, slug, area_slug, official_name, bncc_component_code, mec_reference, description, updated_at
        ) VALUES (
          :name, :slug, :area_slug, :official_name, :bncc_component_code, :mec_reference, :description, now()
        )
        RETURNING *
        """,
        {
            "name": body.name.strip(),
            "slug": slug,
            "area_slug": body.area_slug,
            "official_name": body.official_name,
            "bncc_component_code": body.bncc_component_code,
            "mec_reference": body.mec_reference,
            "description": body.description,
        },
    )
    assert row
    await _sync_discipline_grades(db, row["id"], body.grade_ids)
    await db.commit()
    return _row_discipline(row, [str(g) for g in body.grade_ids])


@router.patch("/disciplines/{discipline_id}")
async def patch_discipline_v1(
    discipline_id: UUID,
    body: DisciplinePatch,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    _assert_admin(ctx)
    existing = await fetch_one(
        db,
        "SELECT * FROM disciplines WHERE id = CAST(:id AS uuid)",
        {"id": str(discipline_id)},
    )
    if not existing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Disciplina não encontrada")
    if body.area_slug is not None and body.area_slug:
        area = await fetch_one(
            db,
            "SELECT slug FROM curricular_areas WHERE slug = :slug",
            {"slug": body.area_slug},
        )
        if not area:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Área inválida")
    sets: list[str] = ["updated_at = now()"]
    params: dict[str, Any] = {"id": str(discipline_id)}
    for key in (
        "name",
        "slug",
        "area_slug",
        "official_name",
        "bncc_component_code",
        "mec_reference",
        "description",
    ):
        val = getattr(body, key)
        if val is not None:
            sets.append(f"{key} = :{key}")
            params[key] = val.strip() if key == "name" and isinstance(val, str) else val
    row = await fetch_one(
        db,
        f"UPDATE disciplines SET {', '.join(sets)} WHERE id = CAST(:id AS uuid) RETURNING *",
        params,
    )
    if body.grade_ids is not None:
        await _sync_discipline_grades(db, discipline_id, body.grade_ids)
    await db.commit()
    assert row
    gids = await _discipline_grade_ids(db, discipline_id)
    return _row_discipline(row, gids)


@router.delete("/disciplines/{discipline_id}")
async def delete_discipline_v1(
    discipline_id: UUID,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    _assert_admin(ctx)
    in_use = await fetch_one(
        db,
        "SELECT 1 AS x FROM question_item WHERE discipline_id = CAST(:id AS uuid) LIMIT 1",
        {"id": str(discipline_id)},
    )
    if in_use:
        raise HTTPException(status.HTTP_409_CONFLICT, "Disciplina em uso em questões")
    await execute(
        db,
        "DELETE FROM disciplines WHERE id = CAST(:id AS uuid)",
        {"id": str(discipline_id)},
    )
    await db.commit()
    return {"ok": True}
