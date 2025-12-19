#!/usr/bin/env bash
set -e


echo ">>> Starting Airflow Webserver in DEBUG MODE (no gunicorn, stable for Railway)"
exec airflow scheduler
