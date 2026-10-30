"""Entrada de eventos do barramento no central (F1.3).

Recebe entregas por push do Pub/Sub. Hoje: resultado dos satélites (`resultado.aluno.v1`), que é
validado, deduplicado e consolidado em `assessment_result` (idempotente por chave + revisão).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.events.inbound import decode_pubsub_push
from app.events.results_consumer import consolidate_result

router = APIRouter(prefix="/events", tags=["v1-events"])


@router.post("/resultado")
async def on_resultado(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Consumidor de `resultado.aluno.v1` (push do Pub/Sub).

    TODO (segurança): validar o token OIDC do Pub/Sub (settings.pubsub_push_audience) antes de
    processar — o endpoint só deve aceitar entregas da assinatura, não POST de qualquer origem.
    """
    body = await request.json()
    try:
        envelope = decode_pubsub_push(body)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e

    if envelope.event_type != "resultado.aluno.v1":
        # Tipo inesperado: reconhece (ack) para não ficar em reentrega; a assinatura não deveria enviar.
        return {
            "status": "ignored",
            "reason": "event_type",
            "event_id": envelope.event_id,
        }

    try:
        action = await consolidate_result(db, envelope.data)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    await db.commit()
    return {"status": "ok", "action": action, "event_id": envelope.event_id}
