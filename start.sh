#!/bin/bash

# Initialiser DB
airflow db init

# Créer l'utilisateur admin si pas existant
airflow users create \
    --username admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@example.com \
    --password admin \
    || true

# Lancer scheduler en arrière-plan
airflow scheduler &

# Lancer webserver
exec airflow webserver --port ${PORT:-8080}
