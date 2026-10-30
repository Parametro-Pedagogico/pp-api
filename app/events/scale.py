"""Escalas de proficiência (opção A): θ (logito) → escala de reporte + nível.

O motor devolve θ; aqui o central converte para a escala configurada por avaliação e classifica o
nível (AB/B/AD/AV…). A parte pura (transformação e classificação) é testável sem banco; o
carregamento da config e a resolução de escala/etapa consultam o central.
Ver pp-app/docs/contrato-escalas.md.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.v1._sql import fetch_all, fetch_one

# --- Parte pura -------------------------------------------------------------------------------


def compute_proficiency(a: float, b: float, theta: float) -> float:
    """Transformação linear P = a·θ + b (escala de reporte)."""
    return a * theta + b


def classify_level(p: float, cortes: list[float], codigos: list[str]) -> str | None:
    """Nível a partir da proficiência P e dos cortes crescentes.

    Com cortes [c1, c2, c3] e 4 níveis: P<c1 → nível 0; c1≤P<c2 → 1; c2≤P<c3 → 2; P≥c3 → 3.
    """
    if not codigos:
        return None
    i = 0
    for c in cortes:
        if p >= float(c):
            i += 1
    return codigos[min(i, len(codigos) - 1)]


# --- Carregamento da config -------------------------------------------------------------------


def _as_obj(v: Any) -> Any:
    """jsonb pode voltar como str (asyncpg via text()) ou já como objeto."""
    return json.loads(v) if isinstance(v, str) else v


async def load_scale(db: AsyncSession, scale_id: str) -> dict[str, Any] | None:
    """Carrega a escala: níveis (códigos em ordem) + config por (componente, etapa)."""
    s = await fetch_one(
        db, "SELECT id, niveis FROM scale WHERE id = :id", {"id": scale_id}
    )
    if not s:
        return None
    comps = await fetch_all(
        db,
        "SELECT componente, etapa, a, b, cortes FROM scale_component WHERE scale_id = :id",
        {"id": scale_id},
    )
    niveis = [n["codigo"] for n in (_as_obj(s["niveis"]) or [])]
    components = {
        (c["componente"], int(c["etapa"])): {
            "a": c["a"],
            "b": c["b"],
            "cortes": _as_obj(c["cortes"]) or [],
        }
        for c in comps
    }
    return {"id": scale_id, "niveis": niveis, "components": components}


async def _scale_id_for(db: AsyncSession, data: dict[str, Any]) -> str | None:
    macro_id = data.get("macro_id")
    if not macro_id and data.get("prova_id"):
        row = await fetch_one(
            db,
            "SELECT macro_assessment_id FROM assessments WHERE id = CAST(:id AS uuid)",
            {"id": str(data["prova_id"])},
        )
        macro_id = row["macro_assessment_id"] if row else None
    if not macro_id:
        return None
    row = await fetch_one(
        db,
        "SELECT scale_id FROM macro_assessments WHERE id = CAST(:id AS uuid)",
        {"id": str(macro_id)},
    )
    return row["scale_id"] if row and row["scale_id"] else None


async def _etapa_for(db: AsyncSession, data: dict[str, Any]) -> int | None:
    turma_id = data.get("turma_id")
    if not turma_id:
        return None
    row = await fetch_one(
        db,
        """
        SELECT g.grade_year
        FROM classrooms c JOIN grades g ON g.id = c.grade_id
        WHERE c.id = CAST(:id AS uuid)
        """,
        {"id": str(turma_id)},
    )
    return int(row["grade_year"]) if row and row["grade_year"] is not None else None


async def enrich_result_scale(db: AsyncSession, data: dict[str, Any]) -> None:
    """Preenche `proficiencia`, `padrao` e `escala` em `tri.por_componente`, no lugar.

    No-op silencioso quando falta escala, etapa ou θ — o resultado consolida mesmo assim, só sem a
    proficiência (que pode ser preenchida depois, quando a config existir).
    """
    tri = data.get("tri")
    if not isinstance(tri, dict):
        return
    comps = tri.get("por_componente")
    if not isinstance(comps, list) or not comps:
        return

    scale_id = await _scale_id_for(db, data)
    if not scale_id:
        return
    scale = await load_scale(db, scale_id)
    if not scale or not scale["niveis"]:
        return
    etapa = await _etapa_for(db, data)
    if etapa is None:
        return

    for c in comps:
        theta = c.get("theta")
        if theta is None or c.get("proficiencia") is not None:
            continue
        cfg = scale["components"].get((c.get("componente"), etapa))
        if not cfg:
            continue
        p = compute_proficiency(float(cfg["a"]), float(cfg["b"]), float(theta))
        c["proficiencia"] = round(p, 1)
        c["padrao"] = classify_level(p, cfg["cortes"], scale["niveis"])
        c["escala"] = scale_id
