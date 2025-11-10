#!/bin/bash
# Initialiser la base Airflow (SQLite par défaut pour dev)
airflow db migrate
airflow users create \
    --username admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@example.com \
    --password admin \
    || true  # ignore si l'utilisateur existe

# Lancer scheduler en arrière-plan
airflow scheduler &

# Lancer webserver (Railway expose par défaut le PORT)
airflow webserver --port $PORT
