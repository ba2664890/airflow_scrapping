#!/usr/bin/env bash
set -e

# Seul le webserver (ou quand lancé sans arguments) doit initialiser la DB
if [ -z "$1" ] || [ "$1" = "webserver" ]; then
    echo ">>> Initializing Airflow database..."
    airflow db init

    echo ">>> Creating admin user if it doesn't exist..."
    airflow users create \
        --username admin \
        --firstname Admin \
        --lastname User \
        --role Admin \
        --email admin@example.com \
        --password admin || true
fi

# Déterminer quel service lancer
if [ "$1" = "scheduler" ]; then
    echo ">>> Starting Airflow Scheduler..."
    exec airflow scheduler
else
    echo ">>> Starting Airflow Webserver..."
    PORT="${PORT:-8080}"
    exec airflow webserver --port "$PORT"
fi
