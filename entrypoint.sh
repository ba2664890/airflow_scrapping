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
    --email admin@example.com

echo ">>> Starting Airflow Webserver"
exec airflow webserver