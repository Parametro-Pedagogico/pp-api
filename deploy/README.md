# Implantação do central (pp-api)

Central na **VM dedicada** (São Paulo) + **Cloud SQL** (Postgres gerenciado), atrás do Caddy. Ver a
topologia em [`../docs/infra-topologia.md`](../docs/infra-topologia.md) e os comandos GCP (tópicos,
assinaturas, IAM, bucket) em [`../docs/infra-gcp.md`](../docs/infra-gcp.md).

> Nenhum dado pessoal, segredo ou IP entra no Git. `.env` fica fora do versionamento.

## Arquivos

- `docker-compose.yml` — Cloud SQL Auth Proxy + API (uvicorn) + **relay** da outbox.
- `env.producao.modelo` — variáveis; copie para `.env` e preencha (segredos via Secret Manager de
  preferência).
- `Caddyfile.modelo` — HTTPS + proxy para a API.

## Passos (resumo)

1. **Cloud SQL**: criar a instância `pp-central` (Postgres), o banco `pp_db` e o usuário da app; aplicar as
   migrations de `migrations/` (uma vez).
2. **VM dedicada**: criar a VM (São Paulo) **com service account anexada** (Pub/Sub + Storage + Cloud SQL
   Client), instalar Docker e Caddy.
3. `cp env.producao.modelo .env` e preencher; `docker compose up -d --build`.
4. Configurar o Caddy (`Caddyfile.modelo`) com o domínio do central.
5. **Barramento**: criar tópicos/assinaturas e a SA do push (ver `infra-gcp.md`); então
   `EVENTS_PUBLISH_ENABLED=true` e preencher `PUBSUB_PUSH_AUDIENCE`.

A VM do **envio** não é tocada nesta etapa.
