-- F0.3 (arquitetura de microsserviços) — tabela outbox para entrega garantida de eventos.
-- O central grava a mudança de estado e a intenção de publicar na MESMA transação (aqui);
-- um relay lê as pendentes e publica no barramento (Pub/Sub) com retry, marcando como enviada
-- só após o publish. Assim nenhum evento se perde se o publish falhar.
-- Ver pp-app/docs/arquitetura-plataforma.md e contrato-evento-resultado.md. Idempotente.

BEGIN;

CREATE TABLE IF NOT EXISTS event_outbox (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  topic           text NOT NULL,
  event_type      text NOT NULL,
  idempotency_key text NOT NULL,
  payload         jsonb NOT NULL,                 -- envelope completo do evento
  status          text NOT NULL DEFAULT 'pending' -- pending | sent | failed
                    CHECK (status IN ('pending', 'sent', 'failed')),
  attempts        integer NOT NULL DEFAULT 0,
  last_error      text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  sent_at         timestamptz
);

-- Busca das pendentes em ordem de criação.
CREATE INDEX IF NOT EXISTS event_outbox_pending_idx
  ON event_outbox (created_at)
  WHERE status <> 'sent';

INSERT INTO pp_schema_migrations (filename)
SELECT '2026-10-23_f0_event_outbox.sql'
WHERE NOT EXISTS (
  SELECT 1 FROM pp_schema_migrations WHERE filename = '2026-10-23_f0_event_outbox.sql'
);

COMMIT;
