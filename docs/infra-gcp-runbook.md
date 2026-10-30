# Runbook de provisionamento (GCP) — ordem real

Passo a passo para subir o **central** (VM + Cloud SQL) e o **barramento**, e o padrão para cada
**satélite** em Cloud Run. Topologia em [`infra-topologia.md`](infra-topologia.md); conceitos em
[`infra-gcp.md`](infra-gcp.md).

> Rode **um bloco por vez** e confira a saída. Troque os domínios pelos reais e confirme o DNS.
> Nada de segredo entra no Git. `--no-allow-unauthenticated` e OIDC protegem os serviços.

## 0. Variáveis e APIs

```bash
export PROJECT=studious-union-475223-m8
export REGION=southamerica-east1
export ZONE=southamerica-east1-b
export CENTRAL_DOMAIN=plataforma.parametropedagogico.com   # ajuste
gcloud config set project "$PROJECT"
export PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')

gcloud services enable \
  sqladmin.googleapis.com pubsub.googleapis.com storage.googleapis.com \
  compute.googleapis.com run.googleapis.com iam.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
```

## 1. Cloud SQL (banco do central)

```bash
gcloud sql instances create pp-central \
  --database-version=POSTGRES_16 --edition=ENTERPRISE \
  --tier=db-custom-2-7680 --region="$REGION" \
  --storage-size=20GB --storage-auto-increase \
  --availability-type=ZONAL          # REGIONAL = HA (mais caro), recomendável depois

gcloud sql databases create pp_db --instance=pp-central
# Senha forte; de preferência guardar no Secret Manager (passo opcional abaixo).
gcloud sql users create pp_app --instance=pp-central --password='TROQUE-POR-FORTE'

# Guarde o connectionName (usado pelo Cloud SQL Auth Proxy no compose):
gcloud sql instances describe pp-central --format='value(connectionName)'
# -> studious-union-475223-m8:southamerica-east1:pp-central
```

## 2. Service accounts + papéis

```bash
# SA do central (a VM roda com ela) e SA do push do Pub/Sub (OIDC).
gcloud iam service-accounts create pp-central --display-name="Central pp-api"
gcloud iam service-accounts create pubsub-push --display-name="Pub/Sub push (OIDC)"

export CENTRAL_SA="pp-central@$PROJECT.iam.gserviceaccount.com"
export PUSH_SA="pubsub-push@$PROJECT.iam.gserviceaccount.com"

# Central: cliente do Cloud SQL (o resto — publicar replicação, ler bucket — é concedido por recurso abaixo).
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:$CENTRAL_SA" --role="roles/cloudsql.client"

# O agente do Pub/Sub precisa poder cunhar tokens OIDC com a SA de push.
gcloud iam service-accounts add-iam-policy-binding "$PUSH_SA" \
  --member="serviceAccount:service-$PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
```

## 3. Barramento (tópicos + DLQ)

```bash
for t in replicacao resultados replicacao-dlq resultados-dlq; do
  gcloud pubsub topics create "$t"
done

# Central publica em replicacao.
gcloud pubsub topics add-iam-policy-binding replicacao \
  --member="serviceAccount:$CENTRAL_SA" --role="roles/pubsub.publisher"

# O agente do Pub/Sub publica nos DLQ.
for dlq in replicacao-dlq resultados-dlq; do
  gcloud pubsub topics add-iam-policy-binding "$dlq" \
    --member="serviceAccount:service-$PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com" \
    --role="roles/pubsub.publisher"
done
```

## 4. Bucket de artefatos

```bash
export BUCKET="gs://$PROJECT-artefatos-provas"
gcloud storage buckets create "$BUCKET" --location="$REGION" --uniform-bucket-level-access
# Central lê (produção/boletins escrevem — concedido às SAs deles no passo 8).
gcloud storage buckets add-iam-policy-binding "$BUCKET" \
  --member="serviceAccount:$CENTRAL_SA" --role="roles/storage.objectViewer"
```

## 5. VM dedicada do central (São Paulo)

```bash
gcloud compute addresses create pp-central-ip --region="$REGION"
gcloud compute addresses describe pp-central-ip --region="$REGION" --format='value(address)'
# -> aponte o DNS de $CENTRAL_DOMAIN para esse IP antes do Caddy emitir o certificado.

gcloud compute firewall-rules create pp-central-web --network=default \
  --allow=tcp:80,tcp:443 --target-tags=pp-central --description="Central: HTTP/HTTPS"

gcloud compute instances create pp-central \
  --machine-type=e2-standard-2 \
  --image-family=ubuntu-2404-lts-amd64 --image-project=ubuntu-os-cloud \
  --boot-disk-size=30GB --boot-disk-type=pd-balanced --no-boot-disk-auto-delete \
  --address=pp-central-ip --tags=pp-central \
  --service-account="$CENTRAL_SA" --scopes=cloud-platform \
  --shielded-secure-boot --zone="$ZONE" --deletion-protection
```

> Diferente da VM do envio (que subiu `--no-service-account`), **esta tem a SA anexada** — é o que
> permite usar Pub/Sub, Storage e Cloud SQL sem chave em arquivo.

## 6. Na VM: Docker, Caddy e subir o central

```bash
gcloud compute ssh pp-central --zone="$ZONE"
# --- dentro da VM ---
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
sudo systemctl enable --now docker
# Caddy (HTTPS automático):
sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update && sudo apt-get install -y caddy

# Código + deploy:
sudo mkdir -p /srv/central && sudo chown "$USER" /srv/central && cd /srv/central
git clone https://github.com/Parametro-Pedagogico/pp-api.git . # ou a branch de deploy
cp deploy/env.producao.modelo deploy/.env   # preencha os segredos e o CLOUDSQL_INSTANCE
cd deploy && sudo docker compose up -d --build

# Caddy:
sudo cp Caddyfile.modelo /etc/caddy/Caddyfile   # ajuste o domínio
sudo systemctl reload caddy

# Migrations (uma vez), pela rede do compose até o proxy do Cloud SQL:
#   use psql apontando ao proxy, ou rode os .sql de migrations/ conforme migrations/README.md
```

## 7. Ligar o barramento no central e a assinatura de resultado

No `deploy/.env` da VM: `EVENTS_PUBLISH_ENABLED=true`, `GCP_PROJECT`, `PUBSUB_PUSH_AUDIENCE=https://$CENTRAL_DOMAIN/v1/events/resultado`, `PUBSUB_PUSH_SERVICE_ACCOUNT=$PUSH_SA`. Depois `docker compose up -d`.

```bash
# (no seu computador) assinatura de resultado -> central, com OIDC e DLQ.
gcloud pubsub subscriptions create resultados-central \
  --topic=resultados \
  --push-endpoint="https://$CENTRAL_DOMAIN/v1/events/resultado" \
  --push-auth-service-account="$PUSH_SA" \
  --push-auth-token-audience="https://$CENTRAL_DOMAIN/v1/events/resultado" \
  --dead-letter-topic=resultados-dlq --max-delivery-attempts=10 --ack-deadline=30
```

## 8. Satélite em Cloud Run (padrão — exemplo: calculadora)

Repetir por satélite. Cada um tem a sua SA e publica em `resultados`; recebe replicação por push.

```bash
export SAT=calculadora
export SAT_SA="$SAT-sa@$PROJECT.iam.gserviceaccount.com"
gcloud iam service-accounts create "$SAT-sa" --display-name="Satélite $SAT"

# Deploy (a partir do repo do satélite; build pelo Cloud Build):
gcloud run deploy "$SAT" --source . --region="$REGION" \
  --no-allow-unauthenticated --service-account="$SAT_SA" \
  --min-instances=0 --max-instances=4
# (motor de TRI/aplicação no TAI: --min-instances=1 só nas janelas de aplicação)

export SAT_URL=$(gcloud run services describe "$SAT" --region="$REGION" --format='value(status.url)')

# O push do Pub/Sub precisa invocar o serviço:
gcloud run services add-iam-policy-binding "$SAT" --region="$REGION" \
  --member="serviceAccount:$PUSH_SA" --role="roles/run.invoker"

# Replicação -> satélite (push no endpoint do consumidor):
gcloud pubsub subscriptions create "replicacao-$SAT" \
  --topic=replicacao \
  --push-endpoint="$SAT_URL/_internal/replication" \
  --push-auth-service-account="$PUSH_SA" \
  --dead-letter-topic=replicacao-dlq --max-delivery-attempts=10 --ack-deadline=30

# Satélite publica resultados:
gcloud pubsub topics add-iam-policy-binding resultados \
  --member="serviceAccount:$SAT_SA" --role="roles/pubsub.publisher"

# Se o satélite grava/ler artefatos:
gcloud storage buckets add-iam-policy-binding "$BUCKET" \
  --member="serviceAccount:$SAT_SA" --role="roles/storage.objectAdmin"
```

## 9. Validação ponta a ponta

1. Alterar uma **escola/turma** no central → ver evento em `event_outbox` e o relay publicar em `replicacao`.
2. O satélite-piloto recebe a replicação (push) e aplica.
3. O satélite publica um **resultado** → `resultados-central` entrega no central → `assessment_result`
   consolidado (com `proficiencia`/`padrao` se a avaliação tiver escala).
4. Conferir DLQ vazio e logs sem 401 (OIDC ok).

## Opcional — segredos no Secret Manager

```bash
printf '%s' 'SENHA-FORTE' | gcloud secrets create pp-db-password --data-file=-
gcloud secrets add-iam-policy-binding pp-db-password \
  --member="serviceAccount:$CENTRAL_SA" --role="roles/secretmanager.secretAccessor"
# e ler no boot da VM / injetar no .env.
```
