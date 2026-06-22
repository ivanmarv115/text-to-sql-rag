#!/usr/bin/env bash
# Manually run Flyway against both demo databases (e.g. to inspect status).
# The stack normally migrates automatically on `docker compose up`; this is for
# ad-hoc use.
#
#   bash shell/migrate.sh info      # show migration status
#   bash shell/migrate.sh migrate   # apply pending migrations
#   bash shell/migrate.sh baseline  # baseline an existing database
#
# Assumes the compose stack's network exists (default: text2sql_default) and the
# db service is reachable as host "db".
set -euo pipefail

CMD="${1:-info}"
NETWORK="${COMPOSE_NETWORK:-text2sql_default}"
PG_USER="${POSTGRES_USER:-app}"
PG_PASSWORD="${POSTGRES_PASSWORD:-app_demo_pw}"
CLINIC_DB="${PG_DBNAME:-clinic_demo}"
CHAINLIT_DB="${CHAINLIT_DB_NAME:-chainlit}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"

run() {
  local db="$1" loc="$2"
  docker run --rm --network "$NETWORK" \
    -v "$HERE/flyway/$loc:/flyway/sql:ro" \
    flyway/flyway:10 \
    -url="jdbc:postgresql://db:5432/$db" \
    -user="$PG_USER" -password="$PG_PASSWORD" \
    -locations=filesystem:/flyway/sql -connectRetries=30 "$CMD"
}

echo ">> clinic database ($CLINIC_DB)"
run "$CLINIC_DB" clinic
echo ">> chainlit database ($CHAINLIT_DB)"
run "$CHAINLIT_DB" chainlit
