-- Fase 2 (perfis) — flag de contrato: administração de usuários pelo técnico da secretaria.
-- Quando ligada no nó da rede, o técnico pode administrar usuários DENTRO da sua rede
-- (sem atribuir papéis de gestor/admin e sem mover usuários para fora da rede).
-- Idempotente.

BEGIN;

ALTER TABLE schools
  ADD COLUMN IF NOT EXISTS network_user_management_enabled boolean NOT NULL DEFAULT false;

INSERT INTO pp_schema_migrations (filename)
SELECT '2026-10-20_fase2_flag_usuarios_tecnico.sql'
WHERE NOT EXISTS (
  SELECT 1 FROM pp_schema_migrations WHERE filename = '2026-10-20_fase2_flag_usuarios_tecnico.sql'
);

COMMIT;
