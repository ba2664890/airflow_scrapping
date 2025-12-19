#!/usr/bin/env bash
set -e

echo ">>> PATH: $PATH"
which airflow || true
airflow version



echo ">>> Starting Airflow Webserver in DEBUG MODE (no gunicorn, stable for Railway)"
exec airflow webserver --port 8080 --debug
