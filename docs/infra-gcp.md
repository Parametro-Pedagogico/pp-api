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

# Segurança do endpoint de resultado (push): o central valida o OIDC da assinatura.
# A audiência deve bater com a configurada na subscription resultados-central.
PUBSUB_PUSH_AUDIENCE=https://<url-do-pp-api>/v1/events/resultado
PUBSUB_PUSH_SERVICE_ACCOUNT=pubsub-push@seu-projeto.iam.gserviceaccount.com
```

> Enquanto `PUBSUB_PUSH_AUDIENCE` estiver vazia, a validação do OIDC fica **desligada** (só para dev
> local). Em produção ela é **obrigatória** — o endpoint `/v1/events/resultado` passa a aceitar apenas
> entregas assinadas pela service account do push.

Rodar o relay periodicamente (Cloud Run job / Cloud Scheduler, ou um systemd timer na VM) chamando
`app.events.relay.relay_once()`. Enquanto `EVENTS_PUBLISH_ENABLED=false`, a outbox apenas acumula com
segurança (nada é publicado).

## Como a replicação funciona (`publish_replication`)

O central é a fonte da verdade; cada satélite tem uma **cópia local** dos dados mestres que usa. Quando um
dado mestre muda no central (uma escola renomeada, uma turma nova, um aluno matriculado, uma prova criada),
o satélite precisa ser avisado. Esse é o papel de `publish_replication`.

Fluxo, passo a passo:

1. **Na mesma transação** que altera o dado, o central chama
   `await publish_replication(db, "escolas", {"id": ..., "version": v, ...campos})`. Isso grava um evento
   `replicacao.escolas` na tabela `event_outbox` (não publica ainda).
2. **Commit atômico:** a mudança do dado e a linha da outbox são confirmadas juntas. Ou as duas persistem,
   ou nenhuma — nunca uma mudança sem o aviso, nem um aviso sem a mudança.
3. **Relay** (processo periódico) lê as pendentes da outbox e **publica** no tópico `replicacao` do Pub/Sub,
   com retry; marca como enviada só após o publish.
4. **Pub/Sub entrega** (push) no endpoint `/_internal/replication` de cada satélite assinante.
5. O satélite **aplica de forma idempotente**: grava só se a `version` recebida for maior que a que ele já
   tem (`apply_replication`). Assim, reentrega e chegada fora de ordem não causam estrago.

Por que outbox em vez de publicar direto: se o central publicasse no meio da transação e o publish falhasse
(ou a transação desse rollback depois), satélite e central ficariam inconsistentes. A outbox garante a
atomicidade; o relay cuida da entrega com retry.

Três camadas de proteção contra duplicação/ordem:
- `event_id` (UUID por mensagem) → deduplicação de transporte;
- chave de negócio `coleção:id:vN` → deduplicação semântica;
- `version` crescente → ordenação (aplica só o mais novo).

**A `version`:** precisa crescer a cada mudança do registro. Duas formas simples:
- uma coluna `version integer` que incrementa no `UPDATE` (mais explícito); ou
- derivar de `updated_at` (ex.: epoch em milissegundos) — sem coluna nova, mas exige `updated_at` confiável.
Recomendação: coluna `version` incremental nas tabelas mestras que serão replicadas.

**O que replicar:** só os campos que os satélites realmente usam, não o banco inteiro. Cada coleção
(`escolas`, `turmas`, `pessoas`/alunos, catálogo de provas) tem o seu "shape" de replicação, definido quando
se instrumenta cada caminho de escrita (F1.1 em diante).

## Onde rodam os serviços (VM × Cloud Run) — dá para manter a VM?

**Sim, a VM atual pode ficar.** A arquitetura não obriga Cloud Run. O que é **gerenciado** pelo GCP e vale
igual nos dois mundos: **Pub/Sub** (o barramento), **Cloud Storage** (artefatos) e **IAM**. Esses não são
servidores que vocês mantêm. O que precisa rodar em algum lugar são os **serviços** (central, satélites) e o
**relay** — e aí a VM serve.

Como a VM se encaixa:
- **Push do Pub/Sub → endpoint HTTPS.** A VM já tem Caddy (HTTPS), então o Pub/Sub entrega push nos serviços
  da VM (ex.: `/_internal/replication`), autenticado por token OIDC que o serviço valida.
- **Relay** como `systemd` timer na VM (a VM está sempre ligada — simples e confiável).
- **Sem cold start.** Serviços sempre quentes na VM são ideais para o que é sensível a latência — o **motor
  de TRI no TAI** e a **aplicação digital**. Esse é um argumento a favor de manter a VM.

Trade-offs:

| | VM (atual) | Cloud Run |
|---|---|---|
| Custo | fixo, 24/7 | por uso, escala a zero |
| Operação | vocês administram (patches, segurança) | gerenciado |
| Escala | manual | automática em picos |
| Latência | previsível, **sem cold start** | **cold start** no 1º request |
| Bom para | serviços sempre ligados e de baixa latência | cargas esporádicas e pesadas |

**Recomendação híbrida (mantendo a VM):**
- **Na VM:** central (`pp-api`), envio (`app_enviar_provas`, já está lá), **motor de TRI** (sempre quente
  para o TAI), aplicação digital, e o **relay** (systemd timer).
- **No Cloud Run (escala a zero):** os workers esporádicos e pesados — **produção de provas** (geração de
  PDF/cartões) e **boletins**. Pagam só quando rodam.
- **Gerenciados (os dois usam):** Pub/Sub, Cloud Storage, IAM.

O mesmo artefato serve aos dois: cada repo polyrepo tem `Dockerfile`; na VM roda como container/systemd, no
Cloud Run como deploy da imagem.

Atenção na VM:
- Anexar uma **service account** à instância com permissão de publicar/assinar Pub/Sub e ler/gravar no
  bucket — assim não há chave em arquivo (credencial via metadata da instância).
- Endpoint público (Caddy) para receber o push, validando o **OIDC** do Pub/Sub.
- VM única é ponto de falha; para serviços críticos, considerar réplica/managed instance group depois
  (otimização posterior, não bloqueia começar).
