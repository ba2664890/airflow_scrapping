#!/usr/bin/env bash
set -e

echo ">>> Running Airflow DB upgrade"
airflow db migrate

echo ">>> Creating admin user if not exists"
airflow users create \
    --username admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --password admin \
    --email admin@example.com

echo ">>> Starting Airflow Webserver"
export WEB_SERVER_MASTER_TIMEOUT=300
airflow webserver --port 8080 --workers 1
