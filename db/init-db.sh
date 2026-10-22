#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS vector;
    CREATE EXTENSION IF NOT EXISTS age;
    -- Set the search path to include age
    ALTER DATABASE $POSTGRES_DB SET search_path = public, age_catalog;
EOSQL
