"""CRUD administrativo do banco de questões (`question_item`)."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from html.parser import HTMLParser
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.v1._paging import PageArgs, paged_response, pagination_params
from app.v1._scope import is_admin_like
from app.v1._sql import execute, fetch_all, fetch_one
from app.v1.question_difficulty import (
    UNCALCULATED_DIFFICULTY_FILTER,
    difficulty_level_label,
    list_difficulty_levels_meta,
    validate_difficulty_level,
)
from app.v1.question_types import (
    list_question_types_meta,
    question_type_label,
    validate_question_type,
)

router = APIRouter(prefix="/question-items", tags=["v1-question-items"])

PP_SOURCE_NAME = "PP"


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"br", "p", "div", "li", "tr"}:
            self._parts.append(" ")

    def get_text(self) -> str:
        text = html.unescape("".join(self._parts))
        return re.sub(r"\s+", " ", text).strip()


def html_to_plain(value: str | None) -> str | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return ""
    if "<" not in raw:
        return raw
    extractor = _HTMLTextExtractor()
    try:
        extractor.feed(raw)
        extractor.close()
    except Exception:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw)).strip()
    return extractor.get_text()


def _assert_platform_admin(ctx: AuthContext) -> None:
    if not is_admin_like(ctx.role):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Apenas administradores da plataforma",
        )


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _serialize_alternative(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "label": row.get("label"),
        "text": row.get("text"),
        "raw_text": row.get("raw_text"),
        "is_correct": bool(row.get("is_correct")),
        "order_index": row.get("order_index"),
        "parameter": row.get("parameter"),
    }


def _serialize_question(
    row: dict[str, Any],
    *,
    alternatives: list[dict[str, Any]] | None = None,
    assessments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "source_id": str(row["source_id"]),
        "source_name": row.get("source_name"),
        "external_id": row.get("external_id"),
        "external_code": row.get("external_code"),
        "description_html": row.get("description_html"),
        "description_raw": row.get("description_raw"),
        "additional_text_html": row.get("additional_text_html"),
        "additional_text_raw": row.get("additional_text_raw"),
        "segment_id": str(row["segment_id"]) if row.get("segment_id") else None,
        "segment_name": row.get("segment_name"),
        "question_type": row.get("question_type"),
        "question_type_label": question_type_label(row.get("question_type")),
        "difficulty_level": row.get("difficulty_level"),
        "difficulty_level_label": difficulty_level_label(row.get("difficulty_level")),
        "has_teacher_comment": bool(row.get("has_teacher_comment")),
        "discipline_external_id": row.get("discipline_external_id"),
        "discipline_id": str(row["discipline_id"]) if row.get("discipline_id") else None,
        "discipline_name": row.get("discipline_catalog_name") or row.get("discipline_name"),
        "discipline_slug": row.get("discipline_slug"),
        "exam_year": row.get("exam_year"),
        "exam_institute": row.get("exam_institute"),
        "area_slug": row.get("area_slug"),
        "area_name": row.get("area_name"),
        "parameters": row.get("parameters"),
        "metadata": row.get("metadata") or {},
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
        "assessments_count": int(row.get("assessments_count") or 0),
        "assessments": assessments
        if assessments is not None
        else (row.get("assessments") or []),
        "alternatives": alternatives if alternatives is not None else [],
    }


class AlternativeIn(BaseModel):
    id: UUID | None = None
    label: str = Field(..., min_length=1, max_length=10)
    text: str | None = None
    raw_text: str | None = None
    is_correct: bool = False
    order_index: int | None = None
    parameter: float | None = None


class QuestionItemCreate(BaseModel):
    """Criação editorial: origem PP é resolvida no servidor."""

    source_id: UUID | None = None
    external_id: str = Field(..., min_length=1, max_length=120)
    external_code: str | None = None
    description_html: str | None = None
    description_raw: str | None = None
    additional_text_html: str | None = None
    additional_text_raw: str | None = None
    segment_id: UUID | None = None
    question_type: str | None = None
    difficulty_level: str | None = None
    has_teacher_comment: bool = False
    discipline_external_id: str | None = None
    discipline_id: UUID | None = None
    exam_year: int | None = None
    exam_institute: str | None = None
    area_slug: str | None = None
    parameters: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    alternatives: list[AlternativeIn] = Field(default_factory=list)


class QuestionItemUpdate(BaseModel):
    source_id: UUID | None = None
    external_id: str | None = Field(default=None, min_length=1, max_length=120)
    external_code: str | None = None
    description_html: str | None = None
    description_raw: str | None = None
    additional_text_html: str | None = None
    additional_text_raw: str | None = None
    segment_id: UUID | None = None
    question_type: str | None = None
    difficulty_level: str | None = None
    has_teacher_comment: bool | None = None
    discipline_external_id: str | None = None
    discipline_id: UUID | None = None
    exam_year: int | None = None
    exam_institute: str | None = None
    area_slug: str | None = None
    parameters: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    alternatives: list[AlternativeIn] | None = None


async def _load_alternatives(db: AsyncSession, question_id: UUID) -> list[dict[str, Any]]:
    rows = await fetch_all(
        db,
        """
        SELECT id, label, text, raw_text, is_correct, order_index, parameter
        FROM question_alternative
        WHERE question_id = CAST(:qid AS uuid)
        ORDER BY COALESCE(order_index, 999), label
        """,
        {"qid": str(question_id)},
    )
    return [_serialize_alternative(r) for r in rows]


async def _load_assessments(db: AsyncSession, question_id: UUID) -> list[dict[str, Any]]:
    rows = await fetch_all(
        db,
        """
        SELECT a.id, a.title, a.type, qa.order_index
        FROM questions_assessments qa
        JOIN assessments a ON a.id = qa.assessment_id
        WHERE qa.question_id = CAST(:qid AS uuid)
        ORDER BY a.title
        """,
        {"qid": str(question_id)},
    )
    return [
        {
            "id": str(r["id"]),
            "title": r.get("title"),
            "type": r.get("type"),
            "order_index": r.get("order_index"),
        }
        for r in rows
    ]


async def _validate_segment_id(db: AsyncSession, segment_id: UUID | None) -> None:
    if segment_id is None:
        return
    row = await fetch_one(
        db,
        "SELECT id FROM segments WHERE id = CAST(:id AS uuid)",
        {"id": str(segment_id)},
    )
    if not row:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Segmento inválido")


async def _validate_discipline_id(
    db: AsyncSession,
    discipline_id: UUID | None,
) -> dict[str, Any] | None:
    if discipline_id is None:
        return None
    row = await fetch_one(
        db,
        """
        SELECT id, name, slug
        FROM disciplines
        WHERE id = CAST(:id AS uuid)
        """,
        {"id": str(discipline_id)},
    )
    if not row:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Disciplina inválida")
    return row


async def _ensure_pp_source(db: AsyncSession) -> str:
    row = await fetch_one(
        db,
        "SELECT id FROM question_source WHERE name = :name",
        {"name": PP_SOURCE_NAME},
    )
    if row:
        return str(row["id"])
    source_id = str(uuid4())
    await execute(
        db,
        """
        INSERT INTO question_source (id, name)
        VALUES (CAST(:id AS uuid), :name)
        """,
        {"id": source_id, "name": PP_SOURCE_NAME},
    )
    return source_id


def _prepare_alternative(alt: AlternativeIn) -> AlternativeIn:
    text = alt.text
    raw = html_to_plain(text) if text is not None else alt.raw_text
    return alt.model_copy(update={"raw_text": raw})


async def _fetch_question_row(db: AsyncSession, question_id: UUID) -> dict[str, Any] | None:
    return await fetch_one(
        db,
        """
        SELECT
          qi.*,
          qs.name AS source_name,
          ca.name AS area_name,
          seg.name AS segment_name,
          disc.name AS discipline_catalog_name,
          (
            SELECT COUNT(*)::int
            FROM questions_assessments qax
            WHERE qax.question_id = qi.id
          ) AS assessments_count
        FROM question_item qi
        JOIN question_source qs ON qs.id = qi.source_id
        LEFT JOIN curricular_areas ca ON ca.slug = qi.area_slug
        LEFT JOIN segments seg ON seg.id = qi.segment_id
        LEFT JOIN disciplines disc ON disc.id = qi.discipline_id
        WHERE qi.id = CAST(:id AS uuid)
        """,
        {"id": str(question_id)},
    )


async def _replace_alternatives(
    db: AsyncSession,
    question_id: UUID,
    alternatives: list[AlternativeIn],
) -> None:
    labels = [a.label.strip() for a in alternatives]
    if len(labels) != len(set(labels)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Labels de alternativas duplicados")
    correct_count = sum(1 for a in alternatives if a.is_correct)
    if alternatives and correct_count != 1:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Informe exatamente uma alternativa correta",
        )

    existing = await fetch_all(
        db,
        """
        SELECT id, label
        FROM question_alternative
        WHERE question_id = CAST(:qid AS uuid)
        """,
        {"qid": str(question_id)},
    )
    by_label = {str(r["label"]): str(r["id"]) for r in existing}
    keep_ids: set[str] = set()

    for idx, alt in enumerate(alternatives):
        prepared = _prepare_alternative(alt)
        label = prepared.label.strip()
        order_index = prepared.order_index if prepared.order_index is not None else idx + 1
        existing_id = by_label.get(label)
        if existing_id:
            await execute(
                db,
                """
                UPDATE question_alternative
                SET text = :text,
                    raw_text = :raw_text,
                    is_correct = :is_correct,
                    order_index = :order_index,
                    parameter = :parameter
                WHERE id = CAST(:id AS uuid)
                """,
                {
                    "id": existing_id,
                    "text": prepared.text,
                    "raw_text": prepared.raw_text,
                    "is_correct": prepared.is_correct,
                    "order_index": order_index,
                    "parameter": prepared.parameter,
                },
            )
            keep_ids.add(existing_id)
        else:
            new_id = str(prepared.id or uuid4())
            await execute(
                db,
                """
                INSERT INTO question_alternative (
                  id, question_id, label, text, raw_text, is_correct, order_index, parameter
                ) VALUES (
                  CAST(:id AS uuid),
                  CAST(:qid AS uuid),
                  :label,
                  :text,
                  :raw_text,
                  :is_correct,
                  :order_index,
                  :parameter
                )
                """,
                {
                    "id": new_id,
                    "qid": str(question_id),
                    "label": label,
                    "text": prepared.text,
                    "raw_text": prepared.raw_text,
                    "is_correct": prepared.is_correct,
                    "order_index": order_index,
                    "parameter": prepared.parameter,
                },
            )
            keep_ids.add(new_id)

    for row in existing:
        alt_id = str(row["id"])
        if alt_id in keep_ids:
            continue
        referenced = await fetch_one(
            db,
            """
            SELECT 1 AS ok
            FROM question_student_responsed
            WHERE response_id = CAST(:id AS uuid)
            LIMIT 1
            """,
            {"id": alt_id},
        )
        if referenced:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Não é possível remover a alternativa '{row['label']}': já há respostas vinculadas",
            )
        await execute(
            db,
            "DELETE FROM question_alternative WHERE id = CAST(:id AS uuid)",
            {"id": alt_id},
        )


@router.get("/meta/sources")
async def list_question_sources_v1(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    _assert_platform_admin(ctx)
    rows = await fetch_all(
        db,
        """
        SELECT id, name, base_url, created_at
        FROM question_source
        ORDER BY name
        """,
    )
    return {
        "items": [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "base_url": r.get("base_url"),
                "created_at": _iso(r.get("created_at")),
            }
            for r in rows
        ]
    }


@router.get("/meta/question-types")
async def list_question_types_v1(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    return {"items": list_question_types_meta()}


@router.get("/meta/areas")
async def list_curricular_areas_v1(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    _assert_platform_admin(ctx)
    rows = await fetch_all(
        db,
        "SELECT slug, name FROM curricular_areas ORDER BY name",
    )
    return {
        "items": [{"slug": r["slug"], "name": r["name"]} for r in rows]
    }


@router.get("/meta/difficulty-levels")
async def list_difficulty_levels_v1(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
):
    _assert_platform_admin(ctx)
    return {"items": list_difficulty_levels_meta()}


@router.get("/meta/disciplines")
async def list_disciplines_v1(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    _assert_platform_admin(ctx)
    rows = await fetch_all(
        db,
        """
        SELECT id, name, slug, area_slug
        FROM disciplines
        ORDER BY name
        """,
    )
    return {
        "items": [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "slug": r.get("slug"),
                "area_slug": r.get("area_slug"),
            }
            for r in rows
        ]
    }


@router.get("")
async def list_question_items_v1(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    paging: Annotated[PageArgs, Depends(pagination_params)],
    q: str | None = Query(None, description="Busca em código/enunciado/disciplina"),
    source_id: UUID | None = None,
    area_slug: str | None = None,
    exam_year: int | None = None,
    segment_id: UUID | None = None,
    discipline_id: UUID | None = None,
    difficulty_level: str | None = None,
    question_type: str | None = None,
):
    _assert_platform_admin(ctx)

    where = ["TRUE"]
    params: dict[str, Any] = {
        "limit": paging.per_page,
        "offset": paging.offset,
    }

    if q and q.strip():
        where.append(
            """(
              qi.external_id ILIKE :q
              OR COALESCE(qi.external_code, '') ILIKE :q
              OR COALESCE(qi.description_raw, '') ILIKE :q
              OR COALESCE(qi.discipline_name, disc.name, '') ILIKE :q
              OR COALESCE(qi.exam_institute, '') ILIKE :q
            )"""
        )
        params["q"] = f"%{q.strip()}%"
    if source_id:
        where.append("qi.source_id = CAST(:source_id AS uuid)")
        params["source_id"] = str(source_id)
    if area_slug:
        where.append("qi.area_slug = :area_slug")
        params["area_slug"] = area_slug
    if exam_year is not None:
        where.append("qi.exam_year = :exam_year")
        params["exam_year"] = exam_year
    if segment_id:
        where.append("qi.segment_id = CAST(:segment_id AS uuid)")
        params["segment_id"] = str(segment_id)
    if discipline_id:
        where.append("qi.discipline_id = CAST(:discipline_id AS uuid)")
        params["discipline_id"] = str(discipline_id)
    if difficulty_level:
        if difficulty_level == UNCALCULATED_DIFFICULTY_FILTER:
            where.append(
                "(qi.difficulty_level IS NULL OR trim(qi.difficulty_level) = '')"
            )
        else:
            where.append("qi.difficulty_level = :difficulty_level")
            params["difficulty_level"] = difficulty_level
    if question_type:
        where.append("qi.question_type = :question_type")
        params["question_type"] = question_type

    where_sql = " AND ".join(where)

    total_row = await fetch_one(
        db,
        f"""
        SELECT COUNT(*)::int AS total
        FROM question_item qi
        LEFT JOIN disciplines disc ON disc.id = qi.discipline_id
        WHERE {where_sql}
        """,
        params,
    )
    total = int((total_row or {}).get("total") or 0)

    rows = await fetch_all(
        db,
        f"""
        SELECT
          qi.*,
          qs.name AS source_name,
          ca.name AS area_name,
          seg.name AS segment_name,
          disc.name AS discipline_catalog_name,
          (
            SELECT COUNT(*)::int
            FROM questions_assessments qax
            WHERE qax.question_id = qi.id
          ) AS assessments_count,
          COALESCE((
            SELECT json_agg(
              json_build_object(
                'id', a.id::text,
                'title', a.title,
                'type', a.type,
                'order_index', qax.order_index
              )
              ORDER BY a.title
            )
            FROM questions_assessments qax
            JOIN assessments a ON a.id = qax.assessment_id
            WHERE qax.question_id = qi.id
          ), '[]'::json) AS assessments
        FROM question_item qi
        JOIN question_source qs ON qs.id = qi.source_id
        LEFT JOIN curricular_areas ca ON ca.slug = qi.area_slug
        LEFT JOIN segments seg ON seg.id = qi.segment_id
        LEFT JOIN disciplines disc ON disc.id = qi.discipline_id
        WHERE {where_sql}
        ORDER BY qi.updated_at DESC NULLS LAST, qi.created_at DESC
        LIMIT :limit OFFSET :offset
        """,
        params,
    )

    items = []
    for row in rows:
        assessments = row.get("assessments") or []
        if isinstance(assessments, str):
            assessments = json.loads(assessments)
        items.append(_serialize_question(row, assessments=assessments, alternatives=[]))

    return paged_response(
        page=paging.page,
        per_page=paging.per_page,
        total=total,
        items=items,
    )


@router.get("/{question_id}")
async def get_question_item_v1(
    question_id: UUID,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    _assert_platform_admin(ctx)
    row = await _fetch_question_row(db, question_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Questão não encontrada")
    alternatives = await _load_alternatives(db, question_id)
    assessments = await _load_assessments(db, question_id)
    return _serialize_question(row, alternatives=alternatives, assessments=assessments)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_question_item_v1(
    body: QuestionItemCreate,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    _assert_platform_admin(ctx)

    # Formulário editorial sempre grava na origem PP (ignora source_id do client).
    source_id = await _ensure_pp_source(db)

    if body.area_slug:
        area = await fetch_one(
            db,
            "SELECT slug FROM curricular_areas WHERE slug = :slug",
            {"slug": body.area_slug},
        )
        if not area:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Área curricular inválida")

    await _validate_segment_id(db, body.segment_id)

    try:
        validate_question_type(body.question_type)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    try:
        validate_difficulty_level(body.difficulty_level)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    discipline_row = await _validate_discipline_id(db, body.discipline_id)

    dup = await fetch_one(
        db,
        """
        SELECT id FROM question_item
        WHERE source_id = CAST(:source_id AS uuid) AND external_id = :external_id
        """,
        {"source_id": source_id, "external_id": body.external_id.strip()},
    )
    if dup:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Já existe questão com este external_id nesta origem",
        )

    description_raw = (
        html_to_plain(body.description_html)
        if body.description_html is not None
        else body.description_raw
    )
    additional_text_raw = (
        html_to_plain(body.additional_text_html)
        if body.additional_text_html is not None
        else body.additional_text_raw
    )

    question_id = uuid4()
    await execute(
        db,
        """
        INSERT INTO question_item (
          id, source_id, external_id, external_code,
          description_html, description_raw,
          additional_text_html, additional_text_raw,
          segment_id, question_type, difficulty_level, has_teacher_comment,
          discipline_id, discipline_external_id, discipline_name, discipline_slug,
          exam_year, exam_institute, area_slug, parameters, metadata
        ) VALUES (
          CAST(:id AS uuid), CAST(:source_id AS uuid), :external_id, :external_code,
          :description_html, :description_raw,
          :additional_text_html, :additional_text_raw,
          CAST(:segment_id AS uuid), :question_type, :difficulty_level, :has_teacher_comment,
          CAST(:discipline_id AS uuid), :discipline_external_id, :discipline_name, :discipline_slug,
          :exam_year, :exam_institute, :area_slug,
          CAST(:parameters AS jsonb), CAST(:metadata AS jsonb)
        )
        """,
        {
            "id": str(question_id),
            "source_id": source_id,
            "external_id": body.external_id.strip(),
            "external_code": body.external_code,
            "description_html": body.description_html,
            "description_raw": description_raw,
            "additional_text_html": body.additional_text_html,
            "additional_text_raw": additional_text_raw,
            "segment_id": str(body.segment_id) if body.segment_id else None,
            "question_type": body.question_type,
            "difficulty_level": body.difficulty_level,
            "has_teacher_comment": body.has_teacher_comment,
            "discipline_id": str(body.discipline_id) if body.discipline_id else None,
            "discipline_external_id": body.discipline_external_id,
            "discipline_name": discipline_row["name"] if discipline_row else None,
            "discipline_slug": discipline_row.get("slug") if discipline_row else None,
            "exam_year": body.exam_year,
            "exam_institute": body.exam_institute,
            "area_slug": body.area_slug,
            "parameters": json.dumps(body.parameters)
            if body.parameters is not None
            else None,
            "metadata": json.dumps(body.metadata or {}),
        },
    )
    await _replace_alternatives(db, question_id, body.alternatives)
    await db.commit()

    row = await _fetch_question_row(db, question_id)
    alternatives = await _load_alternatives(db, question_id)
    return _serialize_question(row or {}, alternatives=alternatives, assessments=[])


@router.patch("/{question_id}")
async def update_question_item_v1(
    question_id: UUID,
    body: QuestionItemUpdate,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    _assert_platform_admin(ctx)
    existing = await _fetch_question_row(db, question_id)
    if not existing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Questão não encontrada")

    data = body.model_dump(exclude_unset=True)
    alternatives = data.pop("alternatives", None)
    # Origem não é editável pelo formulário editorial.
    data.pop("source_id", None)

    if "description_html" in data:
        data["description_raw"] = html_to_plain(data.get("description_html"))
    if "additional_text_html" in data:
        data["additional_text_raw"] = html_to_plain(data.get("additional_text_html"))

    if "area_slug" in data and data["area_slug"]:
        area = await fetch_one(
            db,
            "SELECT slug FROM curricular_areas WHERE slug = :slug",
            {"slug": data["area_slug"]},
        )
        if not area:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Área curricular inválida")

    if "segment_id" in data:
        await _validate_segment_id(db, data.get("segment_id"))

    if "question_type" in data:
        try:
            validate_question_type(data.get("question_type"))
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    if "difficulty_level" in data:
        try:
            validate_difficulty_level(data.get("difficulty_level"))
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    if "discipline_id" in data:
        discipline_row = await _validate_discipline_id(db, data.get("discipline_id"))
        if discipline_row:
            data["discipline_name"] = discipline_row["name"]
            data["discipline_slug"] = discipline_row.get("slug")
        else:
            data["discipline_name"] = None
            data["discipline_slug"] = None

    if data:
        sets = []
        params: dict[str, Any] = {"id": str(question_id)}
        mapping = {
            "external_id": ("external_id", ":external_id"),
            "external_code": ("external_code", ":external_code"),
            "description_html": ("description_html", ":description_html"),
            "description_raw": ("description_raw", ":description_raw"),
            "additional_text_html": ("additional_text_html", ":additional_text_html"),
            "additional_text_raw": ("additional_text_raw", ":additional_text_raw"),
            "segment_id": ("segment_id", "CAST(:segment_id AS uuid)"),
            "question_type": ("question_type", ":question_type"),
            "difficulty_level": ("difficulty_level", ":difficulty_level"),
            "has_teacher_comment": ("has_teacher_comment", ":has_teacher_comment"),
            "discipline_id": ("discipline_id", "CAST(:discipline_id AS uuid)"),
            "discipline_external_id": ("discipline_external_id", ":discipline_external_id"),
            "discipline_name": ("discipline_name", ":discipline_name"),
            "discipline_slug": ("discipline_slug", ":discipline_slug"),
            "exam_year": ("exam_year", ":exam_year"),
            "exam_institute": ("exam_institute", ":exam_institute"),
            "area_slug": ("area_slug", ":area_slug"),
            "parameters": ("parameters", "CAST(:parameters AS jsonb)"),
            "metadata": ("metadata", "CAST(:metadata AS jsonb)"),
        }
        for key, (col, expr) in mapping.items():
            if key not in data:
                continue
            sets.append(f"{col} = {expr}")
            value = data[key]
            if key in ("parameters", "metadata"):
                params[key] = json.dumps(value) if value is not None else None
            elif key == "external_id" and value is not None:
                params[key] = str(value).strip()
            elif key in ("segment_id", "discipline_id"):
                params[key] = str(value) if value is not None else None
            else:
                params[key] = value

        sets.append("updated_at = now()")
        await execute(
            db,
            f"UPDATE question_item SET {', '.join(sets)} WHERE id = CAST(:id AS uuid)",
            params,
        )

    if alternatives is not None:
        await _replace_alternatives(
            db,
            question_id,
            [AlternativeIn.model_validate(a) if isinstance(a, dict) else a for a in alternatives],
        )

    await db.commit()
    row = await _fetch_question_row(db, question_id)
    alts = await _load_alternatives(db, question_id)
    assessments = await _load_assessments(db, question_id)
    return _serialize_question(row or {}, alternatives=alts, assessments=assessments)


@router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question_item_v1(
    question_id: UUID,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    _assert_platform_admin(ctx)
    existing = await _fetch_question_row(db, question_id)
    if not existing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Questão não encontrada")

    linked = await fetch_one(
        db,
        """
        SELECT COUNT(*)::int AS total
        FROM questions_assessments
        WHERE question_id = CAST(:id AS uuid)
        """,
        {"id": str(question_id)},
    )
    if int((linked or {}).get("total") or 0) > 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Questão vinculada a cadernos/avaliações; remova os vínculos antes de excluir",
        )

    await execute(
        db,
        "DELETE FROM question_item WHERE id = CAST(:id AS uuid)",
        {"id": str(question_id)},
    )
    await db.commit()
    return None
