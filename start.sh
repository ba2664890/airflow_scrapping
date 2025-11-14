#!/bin/bash
set -e

echo ">>> Running Airflow DB upgrade"
airflow db upgrade

echo ">>> Starting Airflow Webserver on port ${PORT}"
airflow webserver -p ${PORT}
