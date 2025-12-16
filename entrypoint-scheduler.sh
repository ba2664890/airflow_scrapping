#!/usr/bin/env bash
set -e

echo ">>> PATH: $PATH"
which airflow || true
airflow version

# --- DATABASE INIT ---
echo ">>> Running Airflow DB migration (upgrade)"
airflow db upgrade || airflow db migrate || true

# --- CREATE ADMIN USER ---
echo ">>> Creating admin user if not exists"
airflow users create \
    --username admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --password admin \
    --email admin@example.com || true

# --- IMPORTANT FOR RAILWAY: disable scheduler in web dyno ---
echo ">>> Starting Airflow Webserver ONLY (Railway Dyno)"
export AIRFLOW__CORE__LOAD_EXAMPLES=False
export AIRFLOW__WEBSERVER__WORKERS=1
export AIRFLOW__WEBSERVER__WEB_SERVER_MASTER_TIMEOUT=300

echo ">>> Starting Airflow Webserver in DEBUG MODE (no gunicorn, stable for Railway)"
exec airflow scheduler
