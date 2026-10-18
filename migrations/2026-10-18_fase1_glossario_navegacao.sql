-- Fase 1 (linguagem): nomes do menu em português, conforme docs/glossario.md (pp-app).
-- Idempotente: só altera itens que ainda têm o nome antigo. Pode ser rodada mais de uma vez.

BEGIN;

UPDATE navigation_modules SET name = 'Painel',                updated_at = now() WHERE name = 'Dashboard';
UPDATE navigation_modules SET name = 'Importar resultados',   updated_at = now() WHERE name = 'Imports TRI';
UPDATE navigation_modules SET name = 'Assistente',            updated_at = now() WHERE name = 'Avaliador';
UPDATE navigation_modules SET name = 'Configurar assistente', updated_at = now() WHERE name = 'Config. Avaliador';
UPDATE navigation_modules SET name = 'Situação dos serviços', updated_at = now() WHERE name IN ('Status page', 'Status');

INSERT INTO pp_schema_migrations (filename)
SELECT '2026-10-18_fase1_glossario_navegacao.sql'
WHERE NOT EXISTS (
  SELECT 1 FROM pp_schema_migrations WHERE filename = '2026-10-18_fase1_glossario_navegacao.sql'
);

COMMIT;
