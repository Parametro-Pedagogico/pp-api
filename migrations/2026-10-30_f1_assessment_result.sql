-- F1.3 (consumidor de resultado) — tabela de resultados consolidados no central.
-- Recebe resultado.aluno.v1 dos satélites (envio/aplicação/calculadora). Chave de negócio
-- (prova + aplicação + aluno); last-writer-wins por `revisao` (idempotente, tolera reentrega e
-- fora de ordem). Guarda vetores, TCT e TRI, mais o envelope cru. Ver contrato-evento-resultado.md.
-- Idempotente.

BEGIN;

CREATE TABLE IF NOT EXISTS assessment_result (
  prova_id      uuid NOT NULL,
  schedule_id   uuid NOT NULL,
  aluno_id      uuid NOT NULL,
  macro_id      uuid,
  turma_id      uuid,
  escola_id     uuid,
  modo          text,
  caderno       text,
  revisao       integer NOT NULL DEFAULT 1,
  status        text NOT NULL DEFAULT 'final',
  aplicado_em   timestamptz,
  respostas     jsonb,
  tct           jsonb,
  tri           jsonb,
  raw           jsonb,
  updated_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (prova_id, schedule_id, aluno_id)
);

CREATE INDEX IF NOT EXISTS assessment_result_prova_idx ON assessment_result (prova_id);
CREATE INDEX IF NOT EXISTS assessment_result_escola_idx ON assessment_result (escola_id);

INSERT INTO pp_schema_migrations (filename)
SELECT '2026-10-30_f1_assessment_result.sql'
WHERE NOT EXISTS (
  SELECT 1 FROM pp_schema_migrations WHERE filename = '2026-10-30_f1_assessment_result.sql'
);

COMMIT;
