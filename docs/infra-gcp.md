# Infra GCP do barramento (F0) — comandos prontos

Provisionamento da parte de infraestrutura da F0 que **não** é código: tópicos/assinaturas Pub/Sub,
bucket de artefatos e identidades de serviço. Rodar com a conta/projeto certos; revisar antes de aplicar.
Ver a visão geral em [`../../pp-app/docs/arquitetura-plataforma.md`](../../pp-app/docs/arquitetura-plataforma.md).

> Variáveis: ajuste `PROJECT`, `REGION` e os nomes. Nada aqui grava dado pessoal.

```bash
PROJECT="seu-projeto"
REGION="southamerica-east1"
gcloud config set project "$PROJECT"
```

## 1. Tópicos Pub/Sub

```bash
# Replicação de dados mestres (central -> satélites) e resultados (satélites -> central).
gcloud pubsub topics create replicacao
gcloud pubsub topics create resultados

# Dead-letter para o que falhar o número máximo de entregas.
gcloud pubsub topics create replicacao-dlq
gcloud pubsub topics create resultados-dlq
```

## 2. Assinaturas (push, para Cloud Run)

Cada satélite assina `replicacao`; o central assina `resultados`. Push entrega no endpoint
`/_internal/replication` (satélite) ou no consumidor de resultados (central), autenticado por OIDC.

```bash
# Exemplo: um satélite recebe replicação no seu endpoint de push.
gcloud pubsub subscriptions create replicacao-calculadora \
  --topic=replicacao \
  --push-endpoint="https://<url-do-servico>/_internal/replication" \
  --push-auth-service-account="pubsub-push@${PROJECT}.iam.gserviceaccount.com" \
  --dead-letter-topic=replicacao-dlq \
  --max-delivery-attempts=10 \
  --ack-deadline=30

# O central recebe os resultados.
gcloud pubsub subscriptions create resultados-central \
  --topic=resultados \
  --push-endpoint="https://<url-do-pp-api>/v1/events/resultado" \
  --push-auth-service-account="pubsub-push@${PROJECT}.iam.gserviceaccount.com" \
  --dead-letter-topic=resultados-dlq \
  --max-delivery-attempts=10 \
  --ack-deadline=30
```

## 3. Identidades de serviço (IAM)

```bash
# Conta que o Pub/Sub usa para assinar o push (OIDC) nos serviços.
gcloud iam service-accounts create pubsub-push --display-name="Pub/Sub push (OIDC)"

# O central publica replicação; permita publicar nos tópicos.
gcloud pubsub topics add-iam-policy-binding replicacao \
  --member="serviceAccount:<sa-do-pp-api>@${PROJECT}.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher"

# Satélites publicam resultados.
gcloud pubsub topics add-iam-policy-binding resultados \
  --member="serviceAccount:<sa-do-satelite>@${PROJECT}.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher"
```

## 4. Bucket de artefatos (F0.5)

```bash
gcloud storage buckets create "gs://${PROJECT}-artefatos-provas" \
  --location="$REGION" \
  --uniform-bucket-level-access

# Acesso de serviço (produção grava; aplicador/envio/boletins leem). Sem acesso público.
gcloud storage buckets add-iam-policy-binding "gs://${PROJECT}-artefatos-provas" \
  --member="serviceAccount:<sa-da-producao>@${PROJECT}.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"
```

## 5. Ligar a publicação no central

Depois que os tópicos existem, ligar o relay da outbox no `pp-api`:

```bash
# .env do pp-api
GCP_PROJECT=seu-projeto
EVENTS_PUBLISH_ENABLED=true
PUBSUB_TOPIC_REPLICATION=replicacao
PUBSUB_TOPIC_RESULTS=resultados
```

Rodar o relay periodicamente (Cloud Run job / Cloud Scheduler) chamando `app.events.relay.relay_once()`.
Enquanto `EVENTS_PUBLISH_ENABLED=false`, a outbox apenas acumula com segurança (nada é publicado).
