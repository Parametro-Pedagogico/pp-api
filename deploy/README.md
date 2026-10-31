# Implantação do central (pp-api) — Cloud Run

Tudo em **Cloud Run + Cloud SQL + Pub/Sub**, sem VM. O central é um serviço Cloud Run público (o frontend
e o push do Pub/Sub o chamam; a autenticação é da própria app — Firebase + OIDC no endpoint de resultado).
O **relay** da outbox roda como **Cloud Run Job** disparado pelo **Cloud Scheduler**.

Topologia: [`../docs/infra-topologia.md`](../docs/infra-topologia.md) · Passo a passo:
[`../docs/infra-gcp-runbook.md`](../docs/infra-gcp-runbook.md).

> Nenhum segredo entra no Git. Use `--set-secrets` (Secret Manager) para `JWT_SECRET`,
> `REFRESH_TOKEN_PEPPER`, senha do banco e `FIREBASE_PRIVATE_KEY`.

## Arquivos

- `env.cloudrun.modelo` — variáveis do serviço (referência para `--set-env-vars` / `--set-secrets`).
- O `Dockerfile` (raiz do repo) serve para o **serviço** e para o **Job** do relay (muda só o comando).

## Resumo

- **Serviço** `plataforma`: `gcloud run deploy plataforma --source . --allow-unauthenticated`
  `--add-cloudsql-instances=<connectionName> --service-account=<central-sa> --min-instances=1`.
- **Domínio**: `gcloud run domain-mappings create` para `plataforma.parametropedagogico.com`.
- **Relay**: Cloud Run Job `relay` (comando `python -m app.events.relay_job`) + Cloud Scheduler (1 min).
- **Migrations**: uma vez, via Cloud SQL Auth Proxy + `psql` (Cloud Shell), conforme `migrations/README.md`.

Comandos completos no [runbook](../docs/infra-gcp-runbook.md).
