#!/usr/bin/env bash
set -e

AIRFLOW_BIN="/usr/local/bin/airflow"

echo ">>> Running Airflow DB upgrade"
$AIRFLOW_BIN db upgrade

echo ">>> Creating admin user if not exists"
$AIRFLOW_BIN users create \
    --username admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --password admin \
    --email admin@example.com || true

echo ">>> Starting Airflow Webserver"
export WEB_SERVER_MASTER_TIMEOUT=300
exec $AIRFLOW_BIN webserver --port 8080 --workers 1
