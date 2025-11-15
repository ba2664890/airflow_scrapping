#!/usr/bin/env bash
set -e

# Chemin complet vers le binaire airflow dans l'image officielle
AIRFLOW_CMD="/opt/airflow/venv/bin/airflow"

echo ">>> Running Airflow DB upgrade"
$AIRFLOW_CMD db upgrade

echo ">>> Creating admin user if not exists"
$AIRFLOW_CMD users create \
    --username admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --password admin \
    --email admin@example.com || true

echo ">>> Starting Airflow Webserver"
export WEB_SERVER_MASTER_TIMEOUT=300
exec $AIRFLOW_CMD webserver --port 8080 --workers 1
