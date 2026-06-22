#!/bin/bash
# Runs once, on first initialisation of the Postgres data directory.
# Creates the second (Chainlit/audit) database and the read-only role that the
# Text-to-SQL engine uses to query the clinic database.
set -e

CHAINLIT_DB="${CHAINLIT_DB_NAME:-chainlit}"
RO_USER="${READONLY_DB_USER:-llm_readonly}"
RO_PASS="${READONLY_DB_PASSWORD:-readonly_demo_pw}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
CREATE DATABASE ${CHAINLIT_DB};
CREATE ROLE ${RO_USER} LOGIN PASSWORD '${RO_PASS}';
GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO ${RO_USER};
EOSQL

echo "Initialised database '${CHAINLIT_DB}' and read-only role '${RO_USER}'."
