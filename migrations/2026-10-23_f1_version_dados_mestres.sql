-- F1.1 (replicação) — coluna `version` incremental nos dados mestres + trigger de bump.
-- A cada UPDATE, a trigger incrementa `version`; assim qualquer caminho de escrita gera uma
-- versão nova sem o código precisar lembrar. O consumidor no satélite aplica só o que for mais novo.
-- Começa por schools e classrooms (próximas coleções entram em migrations seguintes). Idempotente.

BEGIN;

ALTER TABLE schools    ADD COLUMN IF NOT EXISTS version integer NOT NULL DEFAULT 1;
ALTER TABLE classrooms ADD COLUMN IF NOT EXISTS version integer NOT NULL DEFAULT 1;

CREATE OR REPLACE FUNCTION bump_row_version() RETURNS trigger AS $$
BEGIN
  NEW.version := OLD.version + 1;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS schools_bump_version ON schools;
CREATE TRIGGER schools_bump_version BEFORE UPDATE ON schools
  FOR EACH ROW EXECUTE FUNCTION bump_row_version();

DROP TRIGGER IF EXISTS classrooms_bump_version ON classrooms;
CREATE TRIGGER classrooms_bump_version BEFORE UPDATE ON classrooms
  FOR EACH ROW EXECUTE FUNCTION bump_row_version();

INSERT INTO pp_schema_migrations (filename)
SELECT '2026-10-23_f1_version_dados_mestres.sql'
WHERE NOT EXISTS (
  SELECT 1 FROM pp_schema_migrations WHERE filename = '2026-10-23_f1_version_dados_mestres.sql'
);

COMMIT;
