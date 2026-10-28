"""Replicação dos dados mestres: mapeia a linha do banco para o "shape" que o satélite recebe.

Só os campos que os satélites usam viajam (não o banco inteiro). Chamar dentro da transação da
escrita, antes do commit, passando a linha retornada por `RETURNING *` (que já traz `version`).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.events.replication import publish_replication

# Campos replicados por coleção. `id` e `version` são obrigatórios.
SCHOOL_FIELDS = [
    "id",
    "version",
    "name",
    "code",
    "city",
    "state",
    "parent",
    "type",
    "network_user_management_enabled",
]
CLASSROOM_FIELDS = [
    "id",
    "version",
    "school_id",
    "academic_year_id",
    "grade_id",
    "code",
    "name",
    "shift",
]


def _shape(row: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    """Seleciona os campos e torna UUIDs serializáveis (str)."""
    out: dict[str, Any] = {}
    for f in fields:
        if f not in row:
            continue
        v = row[f]
        out[f] = str(v) if isinstance(v, uuid.UUID) else v
    return out


async def replicate_school(db: AsyncSession, row: dict[str, Any]) -> None:
    await publish_replication(db, "escolas", _shape(row, SCHOOL_FIELDS))


async def replicate_classroom(db: AsyncSession, row: dict[str, Any]) -> None:
    await publish_replication(db, "turmas", _shape(row, CLASSROOM_FIELDS))


async def replicate_deletion(
    db: AsyncSession, collection: str, record_id: Any, last_version: int
) -> None:
    """Tombstone: avisa o satélite para remover o registro.

    `last_version` é a versão que o registro tinha antes de ser apagado; o tombstone usa a
    próxima (`+1`) para ser mais novo que o último estado replicado (ordenação/idempotência).
    """
    await publish_replication(
        db,
        collection,
        {"id": str(record_id), "version": int(last_version) + 1, "deleted": True},
    )
