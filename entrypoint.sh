#!/usr/bin/env bash
set -e

echo ">>> Running Airflow DB upgrade"
airflow db upgrade

echo ">>> Creating admin user if not exists"
airflow users create \
    --username admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --password admin \
    --email admin@example.com || true

echo ">>> Starting Airflow Webserver"
export WEB_SERVER_MASTER_TIMEOUT=300
exec airflow webserver --port 8080 --workers 1
