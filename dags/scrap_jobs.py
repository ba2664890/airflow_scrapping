"""
DAG Airflow pour l'exécution des spiders Scrapy et la consolidation des données.
Ce DAG orchestre le scraping, la fusion des tables et l'enrichissement NLP.
"""

from datetime import datetime, timedelta
from airflow import DAG
#from airflow.providers.standard.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from airflow.hooks.postgres_hook import PostgresHook
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
import logging
import subprocess
import os

# Configuration par défaut du DAG
default_args = {
    'owner': 'data-engineering',
    'depends_on_past': False,
    'start_date': datetime.now() - timedelta(days=1),
    'email': ['admin@emploi-dakar.com'],
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}



# Définition du DAG
dag = DAG(
    'scrap_jobs_dakar',
    default_args=default_args,
    description="Pipeline ETL pour scraper et enrichir les offres d'emploi au Sénégal",
    schedule='0 */12 * * *',  # ✅ Nouvelle syntaxe
    catchup=False,
    tags=['scraping', 'nlp', 'emploi', 'senegal'],
)


import os
import subprocess
import logging

import os
import subprocess
import logging

def run_scrapy_spider(spider_name, **context):
    """
    Exécute un spider Scrapy dans le projet Scrapy embarqué dans Docker.
    """
    logging.info(f"🚀 Démarrage du spider: {spider_name}")

    # 📌 1) CHEMIN DOCKER OU LOCAL
    scrapy_project_path = "/opt/airflow/scrapy_project" if os.path.exists("/opt/airflow/scrapy_project") else "/home/cardan/Documents/airflow_scrapping"

    # 📌 2) Scrapy est installé via pip
    scrapy_bin = "/home/airflow/.local/bin/scrapy" if os.path.exists("/home/airflow/.local/bin/scrapy") else "/home/cardan/Documents/airflow_scrapping/env_airflow/bin/scrapy"

    # Vérification de l'existence du binaire scrapy
    if not os.path.exists(scrapy_bin):
        logging.warning("⚠️ scrapy introuvable, on tente 'scrapy' depuis le PATH")
        scrapy_bin = "scrapy"

    # 📌 3) Commande Scrapy
    cmd = [scrapy_bin, "crawl", spider_name]

    try:
        result = subprocess.run(
            cmd,
            cwd=scrapy_project_path,   # Très important !
            capture_output=True,
            text=True,
            check=True
        )

        logging.info(f"✅ Spider {spider_name} exécuté avec succès")
        logging.info(result.stdout)

        return f"Spider {spider_name} completed successfully"

    except subprocess.CalledProcessError as e:
        logging.error(f"❌ Erreur lors de l'exécution du spider {spider_name}")
        logging.error(e.stderr)
        raise

def consolidate_tables(**context):
    """
    Fusionne les tables des trois spiders dans la table consolidée.
    """
    logging.info("Début de la consolidation des tables")
    
    postgres_hook = PostgresHook(postgres_conn_id='neon_conn')
    
    # Requête de consolidation
    consolidate_query = """
	INSERT INTO offres_emploi_brutes (
	    id , spider_source, original_id, title, url, location, 
	    company_name, posted_date, source, description, 
	    contract_type, salary, category, sector, experience_level,
	    education_level, nb_positions, expiration_date 
	)

	-- 1️⃣ EMPLOI.DAKAR
	SELECT 
	    gen_random_uuid(),
	   'emploi' AS spider_source,
	    id AS original_id,
	    title,
	    url,
	    location,
	    company_name,
	    CAST(posted_date AS DATE) AS posted_date,
	    source,
	    COALESCE(description_p, description_ul, '') AS description,
	    contract_type,
	    NULL AS salary,
	    NULL AS category,
	    NULL AS sector,
	    NULL AS experience_level,
	    NULL AS education_level,
	    1 AS nb_positions,
	    NULL AS expiration_date
	FROM emplois
	WHERE id IS NOT NULL
	  AND id NOT IN (
	      SELECT original_id FROM offres_emploi_brutes WHERE spider_source = 'emploi'
	  )

	UNION ALL

	-- 2️⃣ SENJOB
	SELECT 
	    gen_random_uuid(),
	    'senjob' AS spider_source,
	    id AS original_id,
	    title,
	    url,
	    location,
	    NULL AS company_name,
	    CAST(posted_date AS DATE) AS posted_date,
	    source,
	    description,
	    contract_type,
	    salaire AS salary,
	    categorie AS category,
	    NULL AS sector,
	    NULL AS experience_level,
	    NULL AS education_level,
	    1 AS nb_positions,
	    CAST(expiration AS DATE) AS expiration_date
	FROM senjobs
	WHERE id IS NOT NULL
	  AND id NOT IN (
	      SELECT original_id FROM offres_emploi_brutes WHERE spider_source = 'senjob'
	  )

	UNION ALL

	-- 3️⃣ EMPLOI_EXPATDAKAR
	SELECT 
	    gen_random_uuid(),
	    'emploi_expatDakar' AS spider_source,
	    id AS original_id,
	    title,
	    url,
	    location,
	    employeur AS company_name,
	    CAST(posted_date AS DATE) AS posted_date,
	    source,
	    description,
	    type_contrat AS contract_type,
	    NULL AS salary,
	    NULL AS category,
	    secteur AS sector,
	    niveau AS experience_level,
	    niveau_etude AS education_level,
	    COALESCE(CAST(nb_postes AS INTEGER), 1) AS nb_positions,
	    NULL AS expiration_date
	FROM emploi_expatdakar
	WHERE id IS NOT NULL
	  AND id NOT IN (
	      SELECT original_id FROM offres_emploi_brutes WHERE spider_source = 'emploi_expatDakar'
	  );
	"""

    
    try:
        postgres_hook.run(consolidate_query)
        logging.info("Consolidation des tables terminée avec succès")
        
        # Comptage des nouveaux enregistrements
        count_query = """
        SELECT COUNT(*) as new_records 
        FROM offres_emploi_brutes 
        WHERE created_at >= CURRENT_DATE - INTERVAL '1 day'
        """
        
        result = postgres_hook.get_first(count_query)
        new_records = result[0] if result else 0
        
        logging.info(f"{new_records} nouvelles offres d'emploi consolidées")
        
        return f"Consolidation completed: {new_records} new records"
        
    except Exception as e:
        logging.error(f"Erreur lors de la consolidation: {e}")
        raise

def get_consolidation_stats(**context):
    """
    Récupère les statistiques de consolidation pour les notifications.
    """
    postgres_hook = PostgresHook(postgres_conn_id='neon_conn')

    
    stats_query = """
    SELECT 
        spider_source,
        COUNT(*) as total_records,
        COUNT(CASE WHEN created_at >= CURRENT_DATE - INTERVAL '1 day' THEN 1 END) as new_records
    FROM offres_emploi_brutes 
    GROUP BY spider_source
    """
    
    try:
        results = postgres_hook.get_records(stats_query)
        stats = {row[0]: {'total': row[1], 'new': row[2]} for row in results}
        
        # Stocker les stats dans XCom pour les notifications
        context['task_instance'].xcom_push(key='consolidation_stats', value=stats)
        
        return stats
        
    except Exception as e:
        logging.error(f"Erreur lors de la récupération des statistiques: {e}")
        raise

# Tâche 1: Exécuter le spider Emploi
task_scrap_emploi = PythonOperator(
    task_id='scrap_emploi_spider',
    python_callable=run_scrapy_spider,
    op_kwargs={'spider_name': 'emploidakar'},
    dag=dag,
)

# Tâche 2: Exécuter le spider Senjob
task_scrap_senjob = PythonOperator(
    task_id='scrap_senjob_spider',
    python_callable=run_scrapy_spider,
    op_kwargs={'spider_name': 'emploi_senjob'},
    dag=dag,
)

# Tâche 3: Exécuter le spider Emploi Expat Dakar
task_scrap_expat = PythonOperator(
    task_id='scrap_expat_dakar_spider',
    python_callable=run_scrapy_spider,
    op_kwargs={'spider_name': 'emploi_expatdakar'},
    dag=dag,
)

# Tâche 4: Consolider les tables
task_consolidate = PythonOperator(
    task_id='consolidate_tables',
    python_callable=consolidate_tables,
    dag=dag,
)

# Tâche 5: Récupérer les statistiques
task_get_stats = PythonOperator(
    task_id='get_consolidation_stats',
    python_callable=get_consolidation_stats,
    dag=dag,
)


from pathlib import Path

sql_path = "/opt/airflow/scripts/init.sql" if os.path.exists("/opt/airflow/scripts/init.sql") else "/home/cardan/Documents/airflow_scrapping/scripts/init.sql"
SQL_FILE = Path(sql_path)
init_sql = SQL_FILE.read_text(encoding='utf-8')

init_ts = SQLExecuteQueryOperator(
    task_id='init_timestamps',
    conn_id='postgres_default',
    sql=init_sql,          # ← on passe le **texte**, pas le nom du fichier
    dag=dag,
)

# Tâche 6: Nettoyer les données temporaires
task_cleanup = SQLExecuteQueryOperator(
    task_id='cleanup_temp_tables',
    conn_id='postgres_default',  # Nouveau paramètre
    sql="""
    -- Nettoyer les tables temporaires si elles existent
    DROP TABLE IF EXISTS temp_emploi_data;
    DROP TABLE IF EXISTS temp_senjob_data;
    DROP TABLE IF EXISTS temp_expat_data;
    """,
    dag=dag,
)


# Définir les dépendances
task_scrap_emploi >> task_scrap_senjob >> task_scrap_expat >> init_ts >> task_consolidate >> task_get_stats >> task_cleanup
