#!/usr/bin/env bash
set -e

# Mapper DATABASE_URL vers la variable attendue par Airflow à l'exécution
if [ -n "$DATABASE_URL" ]; then
    echo ">>> Mapping DATABASE_URL to AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"
    export AIRFLOW__DATABASE__SQL_ALCHEMY_CONN="$DATABASE_URL"
fi

# Seul le webserver (ou quand lancé sans arguments ou mode "all") doit initialiser la DB
if [ -z "$1" ] || [ "$1" = "webserver" ] || [ "$1" = "all" ]; then
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
elif [ "$1" = "all" ]; then
    echo ">>> Starting Airflow Webserver and Scheduler (All-in-one)..."
    airflow scheduler &
    PORT="${PORT:-8080}"
    exec airflow webserver --port "$PORT"
else
    echo ">>> Starting Airflow Webserver..."
    PORT="${PORT:-8080}"
    exec airflow webserver --port "$PORT"
fi
