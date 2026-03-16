#!/usr/bin/env bash
set -e

echo ">>> PATH: $PATH"
which airflow || true
airflow version

# Execute the command passed as arguments
exec "$@"
