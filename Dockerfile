# ------ Base officielle ------
FROM apache/airflow:2.7.0-python3.11

# ------ Root : deps système ------
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    libpq-dev \
    gcc \
    curl \
    wget \
    gnupg \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpangocairo-1.0-0 \
    libxkbcommon0 \
    libgtk-3-0 \
    libpango-1.0-0 \
    libcairo2 \
    libx11-xcb1 \
 && rm -rf /var/lib/apt/lists/*

# ------ Utilisateur airflow ------
USER airflow

# Copier requirements.txt
COPY requirements.txt .

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Télécharger le modèle spacy
RUN python -m spacy download fr_core_news_sm

# ------ Playwright ------
RUN python -m playwright install chromium


# ------ Copier projet ------
WORKDIR /opt/airflow
COPY --chown=airflow:airflow . .

# ------ Railway/Render injecte $PORT et $DATABASE_URL ------
ENV AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=$DATABASE_URL
ENV AIRFLOW__CORE__EXECUTOR=SequentialExecutor
ENV AIRFLOW__API__AUTH_BACKEND=airflow.api.auth.backend.basic_auth

# ------ Scripts de démarrage ------
COPY --chown=airflow:airflow entrypoint.sh /entrypoint.sh
COPY --chown=airflow:airflow start.sh /start.sh
RUN chmod +x /entrypoint.sh /start.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash", "/start.sh"]
