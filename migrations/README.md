# Migrations da branch de implementações

Arquivos SQL aplicados em ordem de nome, uma única vez por banco. Cada arquivo registra a si mesmo em
`pp_schema_migrations` e é idempotente.

Aplicar num banco (dev ou outro ambiente, sempre com backup antes):

```bash
psql "$DATABASE_URL_PSQL" -v ON_ERROR_STOP=1 -f migrations/<arquivo>.sql
```

No ambiente local (`pp-app/dev`), o banco é recriado do zero com `docker compose down -v` e as migrations
desta pasta podem ser aplicadas com:

```bash
docker compose exec -T db psql -U postgres -d pp_db -v ON_ERROR_STOP=1 < ../../pp-api/migrations/<arquivo>.sql
```
