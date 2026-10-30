"""Loop do relay da outbox — processo próprio (na VM/compose do central).

Publica as pendentes da outbox a cada `RELAY_INTERVAL_SECONDS`. Falha de um ciclo é registrada e o
loop segue (os itens ficam na outbox e são retentados). Rodar como serviço ao lado do `pp-api`.

    python -m app.events.relay_loop
"""

from __future__ import annotations

import asyncio
import logging
import os

from app.events.relay import relay_once

logger = logging.getLogger("relay")


async def main() -> None:
    interval = float(os.environ.get("RELAY_INTERVAL_SECONDS", "5"))
    logger.info("relay iniciado (intervalo=%ss)", interval)
    while True:
        try:
            n = await relay_once()
            if n:
                logger.info("relay: %d evento(s) publicado(s)", n)
        except Exception:  # noqa: BLE001 - registra e continua; a outbox retenta
            logger.exception("relay: falha no ciclo")
        await asyncio.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    asyncio.run(main())
