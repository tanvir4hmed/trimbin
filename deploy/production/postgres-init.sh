#!/bin/sh
set -eu
password="$(cat /run/secrets/postgres_writer)"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=writer_password="$password" <<'SQL'
CREATE ROLE trimbin_writer LOGIN PASSWORD :'writer_password';
GRANT CONNECT ON DATABASE trimbin TO trimbin_writer;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO trimbin_writer;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO trimbin_writer;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO trimbin_writer;
SQL
