"""Relay da outbox como execução única — para Cloud Run Job (disparado pelo Cloud Scheduler).

Publica as pendentes uma vez e sai. O Scheduler chama o Job periodicamente (ex.: a cada 1 min).
Para rodar como loop contínuo (VM/local), use `app.events.relay_loop`.

    python -m app.events.relay_job
"""

from __future__ import annotations

import asyncio
import logging

from app.events.relay import relay_once


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    n = asyncio.run(relay_once())
    logging.getLogger("relay").info("relay: %d evento(s) publicado(s)", n)


if __name__ == "__main__":
    main()
