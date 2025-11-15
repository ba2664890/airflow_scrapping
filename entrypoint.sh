#!/usr/bin/env bash
set -e

AIRFLOW_CMD="$HOME/.local/bin/airflow"

echo ">>> Running Airflow DB upgrade"
$AIRFLOW_CMD db migrate

echo ">>> Creating admin user if not exists"
$AIRFLOW_CMD users create \
    --username admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --password admin \
    --email admin@example.com

echo ">>> Starting Airflow Webserver"
export WEB_SERVER_MASTER_TIMEOUT=300
exec $AIRFLOW_CMD webserver --port 8080 --workers 1