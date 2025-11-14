#!/usr/bin/env bash
set -e

echo ">>> Running Airflow DB upgrade"
airflow db migrate

echo ">>> Creating admin user if not exists"


echo ">>> Starting Airflow Webserver"
exec airflow webserver