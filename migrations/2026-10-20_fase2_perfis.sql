-- Fase 2 (perfis): novos papéis coordenador, diretor, técnico da secretaria e secretário.
-- Conforme docs/matriz-perfis.md (pp-app), aprovada pela equipe em 2026-10-20.
--
-- Cria apenas as IDENTIDADES dos papéis (role_definitions + aliases). O que cada papel vê no
-- menu (role_module_access) é configurado na tela de matriz de acesso do administrador, ou numa
-- migration de dados posterior quando os códigos dos módulos de produção estiverem confirmados;
-- enquanto não houver linhas, o app usa o menu padrão por papel (fallback estático no pp-app).
--
-- Decisões da matriz:
--   - diretor: mesmo acesso do gestor escolar (school_admin). É papel próprio só para nome/rótulo;
--     o backend o trata como school_admin (escopo e autorização).
--   - coordenador: foco pedagógico da escola; lança presença; não administra usuários.
--   - tecnico_secretaria: operação da rede (aplicações, envio, importação); usuários só com flag de contrato.
--   - secretario: visão estratégica da rede (indicadores e comparação), só leitura.
--   - Todos com scope_type = 'school'. Rede/secretaria = nó em que o perfil é pendurado (hierarquia por parent).
--
-- Idempotente: pode ser rodada mais de uma vez.

BEGIN;

-- 1) Papéis novos (não mexe nos existentes). sort_order após os base (10..40).
INSERT INTO role_definitions (code, name, description, scope_type, is_system, is_active, sort_order)
VALUES
  ('diretor',            'Diretor',                'Direção da escola: mesma visão do gestor escolar (a escola inteira, inclusive usuários).', 'school', false, true, 22),
  ('coordenador',        'Coordenador',            'Coordenação pedagógica da escola: turmas, avaliações, presença e resultados.',             'school', false, true, 24),
  ('tecnico_secretaria', 'Técnico da secretaria',  'Operação da rede: acompanhamento das escolas, aplicações, envio e importação dos cartões.', 'school', false, true, 26),
  ('secretario',         'Secretário de Educação', 'Visão estratégica da rede: indicadores consolidados e comparação entre escolas.',          'school', false, true, 28)
ON CONFLICT (code) DO UPDATE
  SET name        = EXCLUDED.name,
      description = EXCLUDED.description,
      scope_type  = EXCLUDED.scope_type,
      is_active   = true,
      updated_at  = now();

-- 2) Grafias alternativas aceitas no login/atribuição (enums legados, maiúsculas).
INSERT INTO role_definition_aliases (role_definition_id, alias)
SELECT rd.id, a.alias
FROM role_definitions rd
JOIN (VALUES
  ('diretor',            'DIRETOR'),
  ('coordenador',        'COORDENADOR'),
  ('tecnico_secretaria', 'TECNICO_SECRETARIA'),
  ('tecnico_secretaria', 'tecnico_rede'),
  ('secretario',         'SECRETARIO')
) AS a(code, alias) ON a.code = rd.code
ON CONFLICT (alias) DO NOTHING;

INSERT INTO pp_schema_migrations (filename)
SELECT '2026-10-20_fase2_perfis.sql'
WHERE NOT EXISTS (
  SELECT 1 FROM pp_schema_migrations WHERE filename = '2026-10-20_fase2_perfis.sql'
);

COMMIT;
