# Topologia de implantação (decidida)

Como o ecossistema roda em produção. Decidido com os sócios; o passo a passo de provisionamento está no
[**runbook**](infra-gcp-runbook.md) (conceitos em [`infra-gcp.md`](infra-gcp.md)). Objetivo que guia tudo:
**isolamento por serviço**, **custo ≈ zero quando ocioso** e **parar/implantar um serviço sem afetar os
outros**.

## Quem roda onde

| Serviço | Onde | Estado atual | Observação |
|---|---|---|---|
| **Central** (`pp-api`) | **VM dedicada** (São Paulo) + **Cloud SQL** (Postgres gerenciado) | a provisionar | Fonte da verdade, sempre ligada; roda o **relay** da outbox; Caddy para HTTPS |
| **Motor de TRI** (`cat-cloud-function`) | **Cloud Run** | existe (Cloud Run) | Escala a zero; no TAI, `min-instances≥1` só nas janelas de aplicação (cold start) |
| **Aplicação digital** (fixa+TAI) | **Cloud Run** | a construir | Escala a zero; chama o motor direto |
| **Produção de provas** | **Cloud Run** (worker) | a construir | Geração pesada sob demanda; escala a zero |
| **Boletins** | **Cloud Run** (worker) | a construir | Geração sob demanda; escala a zero |
| **Calculadora** | **Cloud Run** | esboço | Satélite-piloto |
| **Envio** (`app_enviar_provas`) | **VM própria atual, intocada** | em produção | Escolas enviando agora; integra ao barramento depois |
| **Barramento** (Pub/Sub), **artefatos** (Cloud Storage), **banco central** (Cloud SQL) | Gerenciados | a provisionar | — |

## Por que Cloud Run nos satélites (e VM no central)

- **Custo zero ocioso + acordar sob demanda:** Cloud Run escala a zero e **recebe o push** do Pub/Sub a
  qualquer hora. Uma **VM parada não recebe push** (não acorda sozinha) e, ligada, custa 24/7 — logo não
  atende "usar só quando precisar". Por isso satélites = Cloud Run.
- **Isolamento e blast radius:** cada satélite é um serviço Cloud Run próprio, com seu repo, deploy e
  (quando tem estado) seu banco. Parar ou implantar um não toca os demais.
- **Central em VM dedicada:** é a fonte da verdade, precisa estar **sempre ligada** (serve o frontend,
  publica replicação, consome resultado) e com **banco gerenciado** (Cloud SQL, backup/HA). O relay da
  outbox roda junto do central.
- **Latência do TAI:** o motor é o único sensível a cold start; cobre-se com `min-instances≥1` **só** nas
  janelas de aplicação.

## Identidades (service accounts) — uma por serviço

Cada serviço tem a sua SA, com o **mínimo** necessário:

| Serviço | Papéis |
|---|---|
| Central (VM) | `pubsub.publisher` (replicação), `pubsub.subscriber`/`run.invoker` conforme o consumo, `cloudsql.client`, `storage.objectViewer` |
| Satélites (Cloud Run) | `pubsub.publisher` (resultados), `storage.objectAdmin`/`Viewer` no bucket conforme o papel |
| Pub/Sub push | `pubsub-push` (OIDC) com `run.invoker` nos serviços Cloud Run; e autorizada no endpoint do central |

> O push do Pub/Sub carrega um **token OIDC**; o central já valida (`verify_pubsub_push`) e os serviços
> Cloud Run exigem `run.invoker` para a SA do push.

## Rede e entrega

- **Frontend → central**: HTTPS no Caddy da VM do central.
- **Central → satélites (replicação)**: via Pub/Sub (tópico `replicacao`), push nas assinaturas de cada
  satélite (URL do Cloud Run).
- **Satélites → central (resultado)**: via Pub/Sub (tópico `resultados`), push no central
  (`/v1/events/resultado`, com OIDC).
- **Aplicação/Envio ↔ motor de TRI**: chamada HTTPS direta, autenticada serviço-a-serviço (`run.invoker`).
- **Artefatos**: Cloud Storage, lido/escrito pelas SAs dos serviços.

## Ordem de provisionamento (central primeiro)

1. **Cloud SQL** (Postgres) + banco do central; aplicar as migrations.
2. **VM dedicada do central** (São Paulo) + Docker + Caddy; subir `pp-api` + **relay**; SA do central.
3. **Barramento**: tópicos `replicacao`/`resultados` (+ DLQ); SA `pubsub-push`; **bucket** de artefatos.
4. **Ligar o central**: `EVENTS_PUBLISH_ENABLED=true`, `PUBSUB_*`, `PUBSUB_PUSH_AUDIENCE`; assinatura
   `resultados-central` → `/v1/events/resultado`.
5. **Satélite-piloto (calculadora)** em Cloud Run: valida replicação → resultado ponta a ponta.
6. Demais satélites, um a um. **Envio** entra por último (anexar SA à VM dele; trocar o CSV manual por
   evento), sem downtime para as escolas.

## Domínios

- **`app.parametropedagogico.com`** = **frontend** (`pp-app`), já no ar — **intocado**.
- **`plataforma.parametropedagogico.com`** = **central** (`pp-api`), API/consumidor de resultado — subdomínio
  **novo** apontando para a VM do central (um registro A → IP fixo `pp-central-ip`). Sem rename, sem downtime.
- Satélites em Cloud Run usam as URLs `*.run.app` (ou domínios próprios depois); não precisam de subdomínio agora.
- O frontend aponta a base da API para `https://plataforma.parametropedagogico.com`, que entra no
  `CORS_ORIGINS` do central junto com `https://app.parametropedagogico.com`.

## Decisões confirmadas

- **Satélites em Cloud Run** (escala a zero, isolados, acordam no push). ✅
- **Central em VM dedicada + Cloud SQL** (banco gerenciado, separado). ✅
- Região do Cloud SQL e da VM: **São Paulo** (`southamerica-east1`), perto das escolas e do envio. ✅
- **Envio intocado** nesta etapa.

Provisionamento: ver o [runbook](infra-gcp-runbook.md).
