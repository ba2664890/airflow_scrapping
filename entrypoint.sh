#!/usr/bin/env bash
set -e

echo ">>> Running Airflow DB upgrade"
airflow db upgrade

echo ">>> Creating admin user if not exists"
airflow users create \
    --username admin1 \
    --firstname Admin \
    --lastname User \
    --role Admin1 \
    --password admin \
    --email admin@example.com || true

echo ">>> Starting Airflow Webserver"
exec airflow webserver
