#!/bin/bash
# entrypoint.sh
airflow db upgrade  # migre la base
exec "$@"           # lance ensuite le webserver ou scheduler
