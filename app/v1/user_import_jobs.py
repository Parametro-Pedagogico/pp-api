"""Importação assíncrona de usuários (SPEC-IMP-002)."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext
from app.db.session import AsyncSessionLocal
from app.v1._sql import execute, fetch_one

logger = logging.getLogger(__name__)

JOB_STATUS_PENDING = "pending"
JOB_STATUS_PROCESSING = "processing"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_FAILED = "failed"


async def ensure_import_jobs_table(db: AsyncSession) -> None:
    await execute(
        db,
        """
        CREATE TABLE IF NOT EXISTS app_import_jobs (
          id text PRIMARY KEY,
          payload_hash text NOT NULL,
          payload_json jsonb NULL,
          result_json jsonb NULL,
          status text NOT NULL DEFAULT 'completed',
          error_message text NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          started_at timestamptz NULL,
          finished_at timestamptz NULL
        )
        """,
        {},
    )
    await execute(
        db,
        """
        ALTER TABLE app_import_jobs ADD COLUMN IF NOT EXISTS payload_json jsonb NULL
        """,
        {},
    )
    await execute(
        db,
        """
        ALTER TABLE app_import_jobs ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'completed'
        """,
        {},
    )
    await execute(
        db,
        """
        ALTER TABLE app_import_jobs ADD COLUMN IF NOT EXISTS error_message text NULL
        """,
        {},
    )
    await execute(
        db,
        """
        ALTER TABLE app_import_jobs ADD COLUMN IF NOT EXISTS started_at timestamptz NULL
        """,
        {},
    )
    await execute(
        db,
        """
        ALTER TABLE app_import_jobs ADD COLUMN IF NOT EXISTS finished_at timestamptz NULL
        """,
        {},
    )
    await execute(
        db,
        """
        ALTER TABLE app_import_jobs ALTER COLUMN result_json DROP NOT NULL
        """,
        {},
    )


def normalize_import_payload(payload: Any) -> tuple[str, dict[str, Any]]:
    if payload.rows is not None:
        body = {
            "rows": payload.rows,
            "create_firebase_user": payload.create_firebase_user,
            "continue_on_error": payload.continue_on_error,
            "skip_existing_email": payload.skip_existing_email,
        }
    else:
        body = {
            "users": [u.model_dump(mode="json") for u in (payload.users or [])],
            "create_firebase_user": payload.create_firebase_user,
            "continue_on_error": payload.continue_on_error,
            "skip_existing_email": payload.skip_existing_email,
        }
    normalized = json.dumps(body, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest(), body


def _build_bodies(payload: Any) -> tuple[list[tuple[int, Any, dict[str, Any]]], list[dict[str, Any]], int]:
    from app.v1.directory_router import UserCreateBody, _dict_csv_row_to_user_create

    bodies: list[tuple[int, UserCreateBody, dict[str, Any]]] = []
    errors: list[dict[str, Any]] = []
    if payload.rows is not None:
        for i, raw in enumerate(payload.rows):
            try:
                bodies.append(
                    (
                        i,
                        _dict_csv_row_to_user_create(
                            raw,
                            default_create_firebase_user=payload.create_firebase_user,
                        ),
                        raw,
                    )
                )
            except ValueError as ve:
                errors.append({"index": i, "email": raw.get("email"), "error": str(ve)})
                if not payload.continue_on_error:
                    break
        return bodies, errors, len(payload.rows)
    users = payload.users or []
    for i, u in enumerate(users):
        bodies.append((i, u, {}))
    return bodies, errors, len(users)


async def run_users_import(
    db: AsyncSession,
    payload: Any,
    *,
    pre_errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from app.v1.directory_router import _create_user_with_profile, _link_import_profile_to_classroom, _parse_uuid_opt

    bodies, parse_errors, total_in = _build_bodies(payload)
    errors = list(pre_errors or []) + parse_errors
    created: list[dict[str, Any]] = []
    seen_emails: set[str] = set()

    for i, u, orig in bodies:
        email_key = (u.email or "").strip().lower()
        if not email_key:
            errors.append({"index": i, "email": u.email, "error": "email obrigatório"})
            if not payload.continue_on_error:
                break
            continue
        if email_key in seen_emails:
            errors.append({"index": i, "email": u.email, "error": "email duplicado no payload"})
            if not payload.continue_on_error:
                break
            continue
        seen_emails.add(email_key)
        if payload.skip_existing_email:
            exists = await fetch_one(
                db,
                "SELECT id FROM people WHERE lower(email) = :email LIMIT 1",
                {"email": email_key},
            )
            if exists:
                created.append({"index": i, "profile_id": None, "email": u.email, "skipped": "existing_email"})
                continue
        try:
            out = await _create_user_with_profile(db, body=u)
            pid = uuid.UUID(str(out["id"]))
            entry: dict[str, Any] = {"index": i, "profile_id": out["id"], "email": out.get("email")}
            class_id = _parse_uuid_opt(orig.get("classroom_id")) if orig else None
            if class_id:
                try:
                    await _link_import_profile_to_classroom(
                        db, role=u.role, profile_id=pid, classroom_id=class_id
                    )
                    await db.commit()
                    entry["classroom_linked"] = True
                except Exception as link_exc:  # noqa: BLE001
                    await db.rollback()
                    errors.append(
                        {
                            "index": i,
                            "email": u.email,
                            "error": f"Usuário criado; falha ao vincular turma: {link_exc!s}",
                        }
                    )
            created.append(entry)
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            errors.append({"index": i, "email": u.email, "error": str(exc)})
            if not payload.continue_on_error:
                break

    return {
        "ok": len(errors) == 0,
        "created": created,
        "errors": errors,
        "summary": {
            "received": total_in,
            "created_count": len([x for x in created if not x.get("skipped")]),
            "skipped_count": len([x for x in created if x.get("skipped")]),
            "error_count": len(errors),
            "linked_count": len([x for x in created if x.get("classroom_linked")]),
        },
    }


async def create_async_import_job(
    db: AsyncSession,
    payload: Any,
    *,
    idempotency_key: str | None,
) -> dict[str, Any]:
    await ensure_import_jobs_table(db)
    payload_hash, payload_body = normalize_import_payload(payload)
    job_id = idempotency_key or str(uuid.uuid4())

    if idempotency_key:
        existing = await fetch_one(
            db,
            """
            SELECT id, payload_hash, status, result_json
            FROM app_import_jobs WHERE id = :id
            """,
            {"id": idempotency_key},
        )
        if existing:
            if existing["payload_hash"] != payload_hash:
                raise HTTPException(status.HTTP_409_CONFLICT, "idempotency_key reutilizada com payload diferente")
            return _job_response(existing, reused=True)

    await execute(
        db,
        """
        INSERT INTO app_import_jobs (id, payload_hash, payload_json, status, result_json)
        VALUES (:id, :payload_hash, CAST(:payload_json AS jsonb), :status, NULL)
        ON CONFLICT (id) DO NOTHING
        """,
        {
            "id": job_id,
            "payload_hash": payload_hash,
            "payload_json": json.dumps(payload_body, ensure_ascii=True),
            "status": JOB_STATUS_PENDING,
        },
    )
    await db.commit()
    return {
        "job_id": job_id,
        "idempotency_key": job_id,
        "status": JOB_STATUS_PENDING,
        "async": True,
    }


async def process_import_job(job_id: str) -> None:
    async with AsyncSessionLocal() as db:
        try:
            await ensure_import_jobs_table(db)
            row = await fetch_one(
                db,
                "SELECT id, payload_json, status FROM app_import_jobs WHERE id = :id",
                {"id": job_id},
            )
            if not row or row.get("status") not in (JOB_STATUS_PENDING, JOB_STATUS_PROCESSING):
                return
            await execute(
                db,
                """
                UPDATE app_import_jobs
                SET status = :status, started_at = COALESCE(started_at, now())
                WHERE id = :id
                """,
                {"id": job_id, "status": JOB_STATUS_PROCESSING},
            )
            await db.commit()

            payload_data = row.get("payload_json") or {}
            if isinstance(payload_data, str):
                payload_data = json.loads(payload_data)
            from app.v1.directory_router import ImportUsersRequest

            payload = ImportUsersRequest.model_validate(payload_data)
            result = await run_users_import(db, payload)
            await execute(
                db,
                """
                UPDATE app_import_jobs
                SET status = :status,
                    result_json = CAST(:result_json AS jsonb),
                    finished_at = now(),
                    error_message = NULL
                WHERE id = :id
                """,
                {
                    "id": job_id,
                    "status": JOB_STATUS_COMPLETED,
                    "result_json": json.dumps(result, ensure_ascii=True),
                },
            )
            await db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.exception("import job %s failed", job_id)
            await db.rollback()
            await execute(
                db,
                """
                UPDATE app_import_jobs
                SET status = :status,
                    error_message = :err,
                    finished_at = now()
                WHERE id = :id
                """,
                {"id": job_id, "status": JOB_STATUS_FAILED, "err": str(exc)[:2000]},
            )
            await db.commit()


def _job_response(row: dict[str, Any], *, reused: bool = False) -> dict[str, Any]:
    status_val = row.get("status") or JOB_STATUS_COMPLETED
    out: dict[str, Any] = {
        "idempotency_key": row["id"],
        "status": status_val,
        "payload_hash": row.get("payload_hash"),
        "created_at": row.get("created_at"),
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
    }
    if row.get("result_json"):
        out["result"] = row["result_json"]
    if row.get("error_message"):
        out["error_message"] = row["error_message"]
    if reused:
        out["idempotency"] = {"reused": True, "idempotency_key": row["id"]}
    return out


async def get_import_job(db: AsyncSession, job_id: str) -> dict[str, Any]:
    await ensure_import_jobs_table(db)
    row = await fetch_one(
        db,
        """
        SELECT id, payload_hash, result_json, status, error_message,
               created_at, started_at, finished_at
        FROM app_import_jobs
        WHERE id = :id
        """,
        {"id": job_id},
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import job não encontrado")
    return _job_response(row)
