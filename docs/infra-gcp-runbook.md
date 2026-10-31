# Runbook de provisionamento (GCP) — tudo Cloud Run

Sobe o **central** (Cloud Run + Cloud SQL), o **barramento** (Pub/Sub), o **relay** (Cloud Run Job + Cloud
Scheduler) e o padrão de cada **satélite** (Cloud Run). **Sem VM.** Topologia em
[`infra-topologia.md`](infra-topologia.md); conceitos em [`infra-gcp.md`](infra-gcp.md).

> Rode **um bloco por vez** e confira a saída. Segredos ficam no **Secret Manager**, nunca no Git.
> O central é público (o frontend e o push o chamam); a autenticação é da app (Firebase + OIDC no endpoint
> de resultado). Os satélites são privados (`--no-allow-unauthenticated`).

## 0. Variáveis e APIs

```bash
export PROJECT=studious-union-475223-m8
export REGION=southamerica-east1
export CENTRAL_DOMAIN=plataforma.parametropedagogico.com
gcloud config set project "$PROJECT"
export PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')

gcloud services enable \
  sqladmin.googleapis.com pubsub.googleapis.com storage.googleapis.com \
  run.googleapis.com iam.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com cloudscheduler.googleapis.com
```

## 1. Cloud SQL (banco do central)

```bash
gcloud sql instances create pp-central \
  --database-version=POSTGRES_16 --edition=ENTERPRISE \
  --tier=db-custom-2-7680 --region="$REGION" \
  --storage-size=20GB --storage-auto-increase --availability-type=ZONAL

gcloud sql databases create pp_db --instance=pp-central
gcloud sql users create pp_app --instance=pp-central --password='TROQUE-POR-FORTE'

export CONN=$(gcloud sql instances describe pp-central --format='value(connectionName)')
echo "$CONN"   # studious-union-475223-m8:southamerica-east1:pp-central
```

## 2. Segredos (Secret Manager)

```bash
# DATABASE_URL (com a senha), JWT_SECRET, REFRESH_TOKEN_PEPPER, FIREBASE_PRIVATE_KEY.
printf '%s' "postgresql+asyncpg://pp_app:SENHA@/pp_db?host=/cloudsql/$CONN" | gcloud secrets create pp-database-url --data-file=-
printf '%s' "$(openssl rand -base64 48)" | gcloud secrets create pp-jwt-secret --data-file=-
printf '%s' "$(openssl rand -base64 24)" | gcloud secrets create pp-refresh-pepper --data-file=-
# chave privada da service account do Firebase (arquivo PEM):
gcloud secrets create pp-firebase-key --data-file=caminho/para/firebase-private-key.pem
```

## 3. Service accounts + papéis

```bash
gcloud iam service-accounts create pp-central  --display-name="Central pp-api (Cloud Run)"
gcloud iam service-accounts create pubsub-push --display-name="Pub/Sub push (OIDC)"
export CENTRAL_SA="pp-central@$PROJECT.iam.gserviceaccount.com"
export PUSH_SA="pubsub-push@$PROJECT.iam.gserviceaccount.com"

# Central: Cloud SQL + ler os segredos.
gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$CENTRAL_SA" --role="roles/cloudsql.client"
for s in pp-database-url pp-jwt-secret pp-refresh-pepper pp-firebase-key; do
  gcloud secrets add-iam-policy-binding "$s" --member="serviceAccount:$CENTRAL_SA" --role="roles/secretmanager.secretAccessor"
done

# O agente do Pub/Sub cunha tokens OIDC com a SA de push.
gcloud iam service-accounts add-iam-policy-binding "$PUSH_SA" \
  --member="serviceAccount:service-$PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
```

## 4. Tópicos (+ DLQ) e bucket

```bash
for t in replicacao resultados replicacao-dlq resultados-dlq; do gcloud pubsub topics create "$t"; done
gcloud pubsub topics add-iam-policy-binding replicacao \
  --member="serviceAccount:$CENTRAL_SA" --role="roles/pubsub.publisher"
for dlq in replicacao-dlq resultados-dlq; do
  gcloud pubsub topics add-iam-policy-binding "$dlq" \
    --member="serviceAccount:service-$PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com" \
    --role="roles/pubsub.publisher"
done

export BUCKET="gs://$PROJECT-artefatos-provas"
gcloud storage buckets create "$BUCKET" --location="$REGION" --uniform-bucket-level-access
# Central lê/grava (atas/cartões vão para o GCS no Cloud Run).
gcloud storage buckets add-iam-policy-binding "$BUCKET" \
  --member="serviceAccount:$CENTRAL_SA" --role="roles/storage.objectAdmin"
```

## 5. Migrations (uma vez, via Cloud Shell)

```bash
# No Cloud Shell, com o repo clonado:
curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.14.1/cloud-sql-proxy.linux.amd64
chmod +x cloud-sql-proxy && ./cloud-sql-proxy "$CONN" &
export PGPASSWORD='SENHA'
for f in migrations/*.sql; do
  psql "host=127.0.0.1 port=5432 dbname=pp_db user=pp_app" -v ON_ERROR_STOP=1 -f "$f"
done
```

## 6. Deploy do central (Cloud Run) + domínio

```bash
# A partir da raiz do repo pp-api (usa o Dockerfile):
gcloud run deploy plataforma --source . --region="$REGION" \
  --service-account="$CENTRAL_SA" \
  --add-cloudsql-instances="$CONN" \
  --allow-unauthenticated \
  --min-instances=1 --max-instances=4 --cpu=1 --memory=512Mi \
  --set-secrets="DATABASE_URL=pp-database-url:latest,JWT_SECRET=pp-jwt-secret:latest,REFRESH_TOKEN_PEPPER=pp-refresh-pepper:latest,FIREBASE_PRIVATE_KEY=pp-firebase-key:latest" \
  --set-env-vars="GCP_PROJECT=$PROJECT,EVENTS_PUBLISH_ENABLED=true,PUBSUB_TOPIC_REPLICATION=replicacao,PUBSUB_TOPIC_RESULTS=resultados,PUBSUB_PUSH_AUDIENCE=https://$CENTRAL_DOMAIN/v1/events/resultado,PUBSUB_PUSH_SERVICE_ACCOUNT=$PUSH_SA,CORS_ORIGINS=https://app.parametropedagogico.com,ATTENDANCE_SHEET_STORAGE_BACKEND=gcs,GCS_ATTENDANCE_SHEETS_BUCKET=$PROJECT-artefatos-provas,FIREBASE_PROJECT_ID=SEU_FIREBASE,FIREBASE_CLIENT_EMAIL=SEU_FIREBASE_CLIENT_EMAIL"

# Domínio (verifique a posse do domínio no Search Console antes):
gcloud beta run domain-mappings create --service=plataforma --domain="$CENTRAL_DOMAIN" --region="$REGION"
gcloud beta run domain-mappings describe --domain="$CENTRAL_DOMAIN" --region="$REGION" \
  --format='value(status.resourceRecords)'   # crie no DNS os registros que aparecem aqui
```

> Se a região **não** oferecer *domain mapping*, use um **Load Balancer HTTPS externo com NEG serverless**
> apontando para o serviço `plataforma` (mesmo domínio, mesma audiência OIDC).

## 7. Relay como Cloud Run Job + Cloud Scheduler

```bash
gcloud run jobs deploy relay --source . --region="$REGION" \
  --service-account="$CENTRAL_SA" \
  --add-cloudsql-instances="$CONN" \
  --set-secrets="DATABASE_URL=pp-database-url:latest" \
  --set-env-vars="GCP_PROJECT=$PROJECT,EVENTS_PUBLISH_ENABLED=true,PUBSUB_TOPIC_REPLICATION=replicacao,PUBSUB_TOPIC_RESULTS=resultados" \
  --command="python" --args="-m,app.events.relay_job"

# O Scheduler pode executar o Job (run.invoker no Job):
gcloud run jobs add-iam-policy-binding relay --region="$REGION" \
  --member="serviceAccount:$CENTRAL_SA" --role="roles/run.invoker"

# Dispara o Job a cada 1 min:
gcloud scheduler jobs create http relay-tick --location="$REGION" \
  --schedule="* * * * *" \
  --uri="https://run.googleapis.com/v2/projects/$PROJECT/locations/$REGION/jobs/relay:run" \
  --http-method=POST --oauth-service-account-email="$CENTRAL_SA"
```

> Latência da replicação ≈ até 1 min (granularidade do Scheduler). Para dado mestre é aceitável.

## 8. Assinatura de resultado (push → central)

```bash
gcloud pubsub subscriptions create resultados-central \
  --topic=resultados \
  --push-endpoint="https://$CENTRAL_DOMAIN/v1/events/resultado" \
  --push-auth-service-account="$PUSH_SA" \
  --push-auth-token-audience="https://$CENTRAL_DOMAIN/v1/events/resultado" \
  --dead-letter-topic=resultados-dlq --max-delivery-attempts=10 --ack-deadline=30
```

## 9. Satélite em Cloud Run (padrão — exemplo: calculadora)

Repetir por satélite. Cada um é **privado** (`--no-allow-unauthenticated`); o push o invoca via IAM.

```bash
export SAT=calculadora
export SAT_SA="$SAT-sa@$PROJECT.iam.gserviceaccount.com"
gcloud iam service-accounts create "$SAT-sa" --display-name="Satélite $SAT"

gcloud run deploy "$SAT" --source . --region="$REGION" \
  --no-allow-unauthenticated --service-account="$SAT_SA" \
  --min-instances=0 --max-instances=4
# motor de TRI/aplicação no TAI: --min-instances=1 só nas janelas de aplicação.

export SAT_URL=$(gcloud run services describe "$SAT" --region="$REGION" --format='value(status.url)')

# O push do Pub/Sub precisa invocar o serviço:
gcloud run services add-iam-policy-binding "$SAT" --region="$REGION" \
  --member="serviceAccount:$PUSH_SA" --role="roles/run.invoker"

# Replicação -> satélite:
gcloud pubsub subscriptions create "replicacao-$SAT" \
  --topic=replicacao --push-endpoint="$SAT_URL/_internal/replication" \
  --push-auth-service-account="$PUSH_SA" \
  --dead-letter-topic=replicacao-dlq --max-delivery-attempts=10 --ack-deadline=30

# Satélite publica resultados (+ bucket, se gravar/ler artefatos):
gcloud pubsub topics add-iam-policy-binding resultados \
  --member="serviceAccount:$SAT_SA" --role="roles/pubsub.publisher"
```

## 10. Validação ponta a ponta

1. `curl -fsS https://$CENTRAL_DOMAIN/` → health do central (HTTPS/cert ok).
2. Alterar uma **escola/turma** → evento em `event_outbox`; o Job `relay` publica em `replicacao` (≤1 min).
3. O satélite-piloto recebe a replicação (push) e aplica.
4. O satélite publica um **resultado** → `resultados-central` → central consolida em `assessment_result`
   (com `proficiencia`/`padrao` se a avaliação tiver escala).
5. DLQs vazios e logs sem 401 (OIDC ok).

## Frontend

Apontar a base da API do `pp-app` para `https://plataforma.parametropedagogico.com` (o `app.` segue sendo o
site, intocado; já está no `CORS_ORIGINS` do central).
