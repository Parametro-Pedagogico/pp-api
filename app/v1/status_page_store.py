"""Componentes da status page (cadastro admin + leitura pública)."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.firebase import firebase_credential_diagnostic
from app.v1._sql import execute, fetch_all, fetch_one

ComponentStatus = Literal["operational", "degraded", "major_outage", "unknown"]
CheckMode = Literal["manual", "probe_database", "probe_firebase_admin"]

_STATUS_RANK = {"operational": 0, "unknown": 1, "degraded": 2, "major_outage": 3}

DEFAULT_COMPONENTS: tuple[dict[str, Any], ...] = (
    {
        "slug": "portal",
        "name": "Portal web",
        "description": "Aplicação web (login, administração e avaliações)",
        "sort_order": 10,
        "check_mode": "manual",
        "manual_status": "operational",
    },
    {
        "slug": "api",
        "name": "API",
        "description": "Serviços REST da plataforma",
        "sort_order": 20,
        "check_mode": "manual",
        "manual_status": "operational",
    },
    {
        "slug": "database",
        "name": "Banco de dados",
        "description": "PostgreSQL — dados da plataforma",
        "sort_order": 30,
        "check_mode": "probe_database",
        "manual_status": "operational",
    },
    {
        "slug": "firebase_admin",
        "name": "Autenticação (servidor)",
        "description": "Firebase Admin — contas e validação de tokens",
        "sort_order": 40,
        "check_mode": "probe_firebase_admin",
        "manual_status": "operational",
    },
)


async def ensure_status_page_tables(db: AsyncSession) -> None:
    await execute(
        db,
        """
        CREATE TABLE IF NOT EXISTS status_page_components (
          id uuid PRIMARY KEY,
          slug text NOT NULL UNIQUE,
          name text NOT NULL,
          description text NULL,
          sort_order int NOT NULL DEFAULT 0,
          check_mode text NOT NULL DEFAULT 'manual',
          manual_status text NOT NULL DEFAULT 'operational',
          is_visible boolean NOT NULL DEFAULT true,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        {},
    )
async def seed_status_components_if_empty(db: AsyncSession) -> None:
    row = await fetch_one(db, "SELECT COUNT(*)::int AS n FROM status_page_components", {})
    if int((row or {}).get("n") or 0) > 0:
        return
    for item in DEFAULT_COMPONENTS:
        await execute(
            db,
            """
            INSERT INTO status_page_components (
              id, slug, name, description, sort_order, check_mode, manual_status, is_visible
            ) VALUES (
              CAST(:id AS uuid), :slug, :name, :description, :sort_order, :check_mode,
              :manual_status, true
            )
            """,
            {
                "id": str(uuid.uuid4()),
                "slug": item["slug"],
                "name": item["name"],
                "description": item.get("description"),
                "sort_order": item["sort_order"],
                "check_mode": item["check_mode"],
                "manual_status": item["manual_status"],
            },
        )


def _merge_status(a: str, b: str) -> ComponentStatus:
    aa = a if a in _STATUS_RANK else "unknown"
    bb = b if b in _STATUS_RANK else "unknown"
    return aa if _STATUS_RANK[aa] >= _STATUS_RANK[bb] else bb  # type: ignore[return-value]


async def _probe_database(db: AsyncSession) -> tuple[ComponentStatus, float | None, str | None]:
    import time

    started = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
        ms = round((time.perf_counter() - started) * 1000, 1)
        return "operational", ms, None
    except Exception as exc:
        ms = round((time.perf_counter() - started) * 1000, 1)
        return "major_outage", ms, str(exc)[:240]


def _probe_firebase_admin() -> tuple[ComponentStatus, str | None, str | None]:
    diag = firebase_credential_diagnostic()
    branch = str(diag.get("credential_branch") or "none")
    detail = str(diag.get("firebase_project_id") or "") or None

    if branch == "none":
        return "degraded", detail, "Credenciais Firebase Admin não configuradas"

    if branch == "FIREBASE_CLIENT_EMAIL_AND_PRIVATE_KEY":
        if not diag.get("has_client_email") or not diag.get("private_key_looks_like_pem"):
            return "degraded", detail, "E-mail ou chave privada inválidos"
        return "operational", detail, None

    if branch == "FIREBASE_CREDENTIALS_PATH":
        ok = bool(diag.get("path_is_file"))
        return ("operational" if ok else "degraded"), detail, None if ok else "Arquivo de credenciais não encontrado"

    if branch == "FIREBASE_CREDENTIALS_JSON":
        ok = int(diag.get("json_length_chars") or 0) > 0
        return ("operational" if ok else "degraded"), detail, None if ok else "JSON de credenciais vazio"

    if branch == "GOOGLE_APPLICATION_CREDENTIALS":
        ok = bool(diag.get("path_is_file"))
        return ("operational" if ok else "degraded"), detail, None if ok else "GOOGLE_APPLICATION_CREDENTIALS inválido"

    return "unknown", detail, f"Branch desconhecida: {branch}"


async def resolve_component_status(
    db: AsyncSession,
    row: dict[str, Any],
) -> dict[str, Any]:
    manual = str(row.get("manual_status") or "operational")
    check_mode = str(row.get("check_mode") or "manual")
    status: ComponentStatus = manual  # type: ignore[assignment]
    latency_ms: float | None = None
    probe_error: str | None = None
    detail: str | None = None
    status_source = "manual"

    if check_mode == "probe_database":
        probed, latency_ms, probe_error = await _probe_database(db)
        status = _merge_status(manual, probed)
        if probed != manual and _STATUS_RANK[probed] > _STATUS_RANK[manual]:
            status_source = "probe"
    elif check_mode == "probe_firebase_admin":
        probed, detail, probe_error = _probe_firebase_admin()
        status = _merge_status(manual, probed)
        if probed != manual and _STATUS_RANK[probed] > _STATUS_RANK[manual]:
            status_source = "probe"

    return {
        "id": str(row["slug"]),
        "component_id": str(row["id"]),
        "name": row["name"],
        "description": row.get("description"),
        "status": status,
        "manual_status": manual,
        "check_mode": check_mode,
        "status_source": status_source,
        "latency_ms": latency_ms,
        "detail": detail,
        "error": probe_error,
    }


async def list_public_status(db: AsyncSession) -> list[dict[str, Any]]:
    await ensure_status_page_tables(db)
    await seed_status_components_if_empty(db)
    await db.commit()
    rows = await fetch_all(
        db,
        """
        SELECT id, slug, name, description, sort_order, check_mode, manual_status, is_visible
        FROM status_page_components
        WHERE is_visible = true
        ORDER BY sort_order ASC, name ASC
        """,
        {},
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(await resolve_component_status(db, row))
    return out


async def list_admin_components(db: AsyncSession) -> list[dict[str, Any]]:
    await ensure_status_page_tables(db)
    await seed_status_components_if_empty(db)
    return await fetch_all(
        db,
        """
        SELECT id, slug, name, description, sort_order, check_mode, manual_status,
               is_visible, created_at, updated_at
        FROM status_page_components
        ORDER BY sort_order ASC, name ASC
        """,
        {},
    )


async def get_admin_component(db: AsyncSession, component_id: uuid.UUID) -> dict[str, Any] | None:
    await ensure_status_page_tables(db)
    return await fetch_one(
        db,
        """
        SELECT id, slug, name, description, sort_order, check_mode, manual_status,
               is_visible, created_at, updated_at
        FROM status_page_components
        WHERE id = CAST(:id AS uuid)
        """,
        {"id": str(component_id)},
    )


async def create_admin_component(db: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    await ensure_status_page_tables(db)
    new_id = uuid.uuid4()
    await execute(
        db,
        """
        INSERT INTO status_page_components (
          id, slug, name, description, sort_order, check_mode, manual_status, is_visible
        ) VALUES (
          CAST(:id AS uuid), :slug, :name, :description, :sort_order, :check_mode,
          :manual_status, :is_visible
        )
        """,
        {
            "id": str(new_id),
            "slug": data["slug"],
            "name": data["name"],
            "description": data.get("description"),
            "sort_order": int(data.get("sort_order") or 0),
            "check_mode": data.get("check_mode") or "manual",
            "manual_status": data.get("manual_status") or "operational",
            "is_visible": bool(data.get("is_visible", True)),
        },
    )
    row = await get_admin_component(db, new_id)
    assert row is not None
    return row


async def update_admin_component(
    db: AsyncSession,
    component_id: uuid.UUID,
    data: dict[str, Any],
) -> dict[str, Any] | None:
    await ensure_status_page_tables(db)
    existing = await get_admin_component(db, component_id)
    if not existing:
        return None
    fields: list[str] = []
    params: dict[str, Any] = {"id": str(component_id)}
    for key, col in (
        ("slug", "slug"),
        ("name", "name"),
        ("description", "description"),
        ("sort_order", "sort_order"),
        ("check_mode", "check_mode"),
        ("manual_status", "manual_status"),
        ("is_visible", "is_visible"),
    ):
        if key in data and data[key] is not None:
            fields.append(f"{col} = :{key}")
            params[key] = data[key]
    if not fields:
        return existing
    fields.append("updated_at = now()")
    await execute(
        db,
        f"UPDATE status_page_components SET {', '.join(fields)} WHERE id = CAST(:id AS uuid)",
        params,
    )
    return await get_admin_component(db, component_id)


async def delete_admin_component(db: AsyncSession, component_id: uuid.UUID) -> bool:
    await ensure_status_page_tables(db)
    row = await fetch_one(
        db,
        "DELETE FROM status_page_components WHERE id = CAST(:id AS uuid) RETURNING id",
        {"id": str(component_id)},
    )
    return row is not None
