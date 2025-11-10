#!/bin/bash

# Initialiser la DB Airflow
airflow db init

# Créer l'utilisateur admin si besoin
airflow users create \
    --username admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@example.com \
    --password admin || true

# Lancer scheduler en arrière-plan
airflow scheduler &

# Lancer webserver sur le PORT fourni par Railway
exec airflow webserver --port ${PORT:-8080}
