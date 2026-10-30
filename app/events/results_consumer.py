"""Consolidação do evento de resultado no central (F1.3).

Recebe o `data` de `resultado.aluno.v1` e faz *upsert* idempotente em `assessment_result`:
chave de negócio (prova + aplicação + aluno), last-writer-wins por `revisao`. Reentrega e chegada
fora de ordem não sobrescrevem um resultado mais novo. Ver contrato-evento-resultado.md.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.events.scale import enrich_result_scale
from app.v1._sql import fetch_all

_REQUIRED = ("prova_id", "schedule_id", "aluno_id")

_UPSERT = """
INSERT INTO assessment_result (
    prova_id, schedule_id, aluno_id, macro_id, turma_id, escola_id,
    modo, caderno, revisao, status, aplicado_em, respostas, tct, tri, raw
) VALUES (
    CAST(:prova_id AS uuid), CAST(:schedule_id AS uuid), CAST(:aluno_id AS uuid),
    CAST(:macro_id AS uuid), CAST(:turma_id AS uuid), CAST(:escola_id AS uuid),
    :modo, :caderno, :revisao, :status, CAST(:aplicado_em AS timestamptz),
    CAST(:respostas AS jsonb), CAST(:tct AS jsonb), CAST(:tri AS jsonb), CAST(:raw AS jsonb)
)
ON CONFLICT (prova_id, schedule_id, aluno_id) DO UPDATE SET
    macro_id = EXCLUDED.macro_id,
    turma_id = EXCLUDED.turma_id,
    escola_id = EXCLUDED.escola_id,
    modo = EXCLUDED.modo,
    caderno = EXCLUDED.caderno,
    revisao = EXCLUDED.revisao,
    status = EXCLUDED.status,
    aplicado_em = EXCLUDED.aplicado_em,
    respostas = EXCLUDED.respostas,
    tct = EXCLUDED.tct,
    tri = EXCLUDED.tri,
    raw = EXCLUDED.raw,
    updated_at = now()
WHERE EXCLUDED.revisao > assessment_result.revisao
RETURNING (xmax = 0) AS inserted
"""


def _json(value: Any) -> str | None:
    return json.dumps(value) if value is not None else None


async def consolidate_result(db: AsyncSession, data: dict[str, Any]) -> str:
    """Upsert idempotente de um resultado de aluno. Não faz commit.

    Retorna a ação: "inserted", "updated" ou "ignored" (reentrega/fora de ordem — nada mudou).
    """
    for k in _REQUIRED:
        if not data.get(k):
            raise ValueError(f"resultado sem campo obrigatório: {k}")

    # Opção A: central aplica a escala da avaliação, preenchendo proficiência/nível (no lugar).
    await enrich_result_scale(db, data)

    params = {
        "prova_id": str(data["prova_id"]),
        "schedule_id": str(data["schedule_id"]),
        "aluno_id": str(data["aluno_id"]),
        "macro_id": str(data["macro_id"]) if data.get("macro_id") else None,
        "turma_id": str(data["turma_id"]) if data.get("turma_id") else None,
        "escola_id": str(data["escola_id"]) if data.get("escola_id") else None,
        "modo": data.get("modo"),
        "caderno": data.get("caderno"),
        "revisao": int(data.get("revisao", 1)),
        "status": data.get("status", "final"),
        "aplicado_em": data.get("aplicado_em"),
        "respostas": _json(data.get("respostas")),
        "tct": _json(data.get("tct")),
        "tri": _json(data.get("tri")),
        "raw": _json(data),
    }
    rows = await fetch_all(db, _UPSERT, params)
    if not rows:
        return "ignored"
    return "inserted" if rows[0]["inserted"] else "updated"
