#!/bin/bash
set -e

# attendre que la DB soit prête
sleep 10

exec airflow scheduler
