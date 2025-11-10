"""
DAG Airflow pour l'enrichissement NLP des offres d'emploi.
Ce DAG traite les données consolidées et extrait des informations sémantiques.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator as PostgresOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
import logging
import sys
import os
import uuid



from nlp_modules.nlp_processor import NLPProcessor
from nlp_modules.skill_extractor import SkillExtractor
from nlp_modules.salary_extractor import SalaryExtractor
from nlp_modules.contract_classifier import ContractClassifier


# ✅ Configuration par défaut du DAG (mise à jour sans email)
default_args = {
    'owner': 'nlp-team',
    'depends_on_past': False,
    'start_date': datetime.now() - timedelta(days=1),
    'retries': 2,
    'retry_delay': timedelta(minutes=10),
    # 🔸 Les paramètres d'email sont dépréciés depuis Airflow 3.1
    # 'email': ['admin@emploi-dakar.com'],
    # 'email_on_failure': True,
    # 'email_on_retry': False,
    # Si tu veux à nouveau des notifications, tu devras utiliser un SmtpNotifier séparé.
}

# Définition du DAG principal
dag = DAG(
    'nlp_enrichment',
    default_args=default_args,
    description='Pipeline NLP pour enrichir les offres d\'emploi',
    schedule ='0 2 * * *',  # Exécution quotidienne à 2h du matin
    catchup=False,
    tags=['nlp', 'enrichment', 'ml', 'text-processing'],
)

def get_jobs_to_process(**context):
    """
    Récupère les offres d'emploi non encore enrichies.
    """
    logging.info("Récupération des offres à enrichir")
    
    postgres_hook = PostgresHook(postgres_conn_id='postgres_default')
    
    query = """
    SELECT 
        b.id, b.title, b.description, b.contract_type, 
        b.salary, b.location, b.company_name, b.spider_source
    FROM offres_emploi_brutes b
    LEFT JOIN offres_emploi_enrichies e ON b.id = e.offre_id
    WHERE e.offre_id IS NULL 
    AND b.description IS NOT NULL 
    AND LENGTH(b.description) > 50
    ORDER BY b.posted_date DESC
    LIMIT 1000
    """
    
    try:
        records = postgres_hook.get_records(query)
        logging.info(f"{len(records)} offres à enrichir trouvées")
        context['task_instance'].xcom_push(key='jobs_to_process', value=records)
        return len(records)
        
    except Exception as e:
        logging.error(f"Erreur lors de la récupération des offres: {e}")
        raise

def process_job_nlp(**context):
    """
    Traite les offres d'emploi avec NLP.
    """
    logging.info("Début du traitement NLP")
    
    ti = context['task_instance']
    jobs = ti.xcom_pull(key='jobs_to_process', task_ids='get_jobs_to_process')
    
    if not jobs:
        logging.info("Aucune offre à traiter")
        return
    
    nlp_processor = NLPProcessor()
    skill_extractor = SkillExtractor()
    salary_extractor = SalaryExtractor()
    contract_classifier = ContractClassifier()
    
    processed_jobs = []
    
    for job in jobs:
        try:
            job_id, title, description, contract_type, salary, location, company_name, spider_source = job
            
            text_to_process = f"{title} {description}"
            
            nlp_results = nlp_processor.process_text(text_to_process)
            skills = skill_extractor.extract_skills(text_to_process)
            salary_info = salary_extractor.extract_salary(text_to_process)
            classified_contract = contract_classifier.classify(text_to_process)
            
            processed_job = {
                'offre_id': job_id,
                'extracted_salary_min': salary_info.get('min_salary'),
                'extracted_salary_max': salary_info.get('max_salary'),
                'extracted_salary_currency': salary_info.get('currency', 'XOF'),
                'extracted_contract_type': classified_contract or contract_type,
                'extracted_experience_years': nlp_results.get('experience_years'),
                'extracted_skills': skills,
                'extracted_sector': nlp_results.get('sector'),
                'extracted_job_category': nlp_results.get('job_category'),
                'sentiment_score': nlp_results.get('sentiment_score'),
                'key_phrases': nlp_results.get('key_phrases', []),
                'job_level': nlp_results.get('job_level'),
                'job_type': nlp_results.get('job_type'),
                'processing_version': 'v1.0',
                'confidence_score': nlp_results.get('confidence_score', 0.8)
            }
            
            processed_jobs.append(processed_job)
            
        except Exception as e:
            logging.error(f"Erreur lors du traitement du job {job[0]}: {e}")
            continue
    
    ti.xcom_push(key='processed_jobs', value=processed_jobs)
    logging.info(f"{len(processed_jobs)} offres traitées avec succès")
    
    return len(processed_jobs)

def save_enriched_data(**context):
    """
    Sauvegarde les données enrichies dans la base de données.
    """
    logging.info("Sauvegarde des données enrichies")
    
    ti = context['task_instance']
    processed_jobs = ti.xcom_pull(key='processed_jobs', task_ids='process_job_nlp')
    
    if not processed_jobs:
        logging.info("Aucune donnée à sauvegarder")
        return
    
    postgres_hook = PostgresHook(postgres_conn_id='postgres_default')
    
    insert_query = """
    INSERT INTO offres_emploi_enrichies (
        id, offre_id, extracted_salary_min, extracted_salary_max, 
        extracted_salary_currency, extracted_contract_type, 
        extracted_experience_years, extracted_skills, extracted_sector,
        extracted_job_category, sentiment_score, key_phrases, 
        job_level, job_type, processing_version, confidence_score
    ) VALUES %s
    """
    
    values = []
    for job in processed_jobs:
        job_id = job.get('id', str(uuid.uuid4()))
        values.append((
            job_id,
            job['offre_id'],
            job['extracted_salary_min'],
            job['extracted_salary_max'],
            job['extracted_salary_currency'],
            job['extracted_contract_type'],
            job['extracted_experience_years'],
            job['extracted_skills'],
            job['extracted_sector'],
            job['extracted_job_category'],
            job['sentiment_score'],
            job['key_phrases'],
            job['job_level'],
            job['job_type'],
            job['processing_version'],
            job['confidence_score']
        ))
    
    try:
        from psycopg2.extras import execute_values
        
        conn = postgres_hook.get_conn()
        cursor = conn.cursor()
        execute_values(cursor, insert_query, values)
        conn.commit()
        cursor.close()
        conn.close()
        
        logging.info(f"{len(values)} enregistrements enrichis sauvegardés")
        
    except Exception as e:
        logging.error(f"Erreur lors de la sauvegarde: {e}")
        raise

def update_job_statistics(**context):
    """
    Met à jour les statistiques du marché de l'emploi.
    """
    logging.info("Mise à jour des statistiques")
    
    postgres_hook = PostgresHook(postgres_conn_id='postgres_default')
    
    stats_queries = [
        """
        INSERT INTO job_statistics (id, metric_name, metric_value, period_start, period_end, category)
        SELECT 
            gen_random_uuid(),
            'offers_by_sector' as metric_name,
            jsonb_build_object('sector', extracted_sector, 'count', count(*)) as metric_value,
            CURRENT_DATE - INTERVAL '1 month' as period_start,
            CURRENT_DATE as period_end,
            'sector_analysis' as category
        FROM offres_emploi_enrichies e
        JOIN offres_emploi_brutes b ON e.offre_id = b.id
        WHERE b.posted_date >= CURRENT_DATE - INTERVAL '1 month'
        AND extracted_sector IS NOT NULL
        GROUP BY extracted_sector
        """,
        """
        INSERT INTO job_statistics (id, metric_name, metric_value, period_start, period_end, category)
        SELECT 
            gen_random_uuid(),
            'offers_by_contract_type' as metric_name,
            jsonb_build_object('contract_type', extracted_contract_type, 'count', count(*)) as metric_value,
            CURRENT_DATE - INTERVAL '1 month' as period_start,
            CURRENT_DATE as period_end,
            'contract_analysis' as category
        FROM offres_emploi_enrichies e
        JOIN offres_emploi_brutes b ON e.offre_id = b.id
        WHERE b.posted_date >= CURRENT_DATE - INTERVAL '1 month'
        AND extracted_contract_type IS NOT NULL
        GROUP BY extracted_contract_type
        """,
        """
        INSERT INTO job_statistics (id, metric_name, metric_value, period_start, period_end, category)
        SELECT 
            gen_random_uuid(),
            'salary_distribution' as metric_name,
            jsonb_build_object(
                'avg_min_salary', AVG(extracted_salary_min),
                'avg_max_salary', AVG(extracted_salary_max),
                'median_salary', PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY (extracted_salary_min + extracted_salary_max) / 2)
            ) as metric_value,
            CURRENT_DATE - INTERVAL '1 month' as period_start,
            CURRENT_DATE as period_end,
            'salary_analysis' as category
        FROM offres_emploi_enrichies e
        JOIN offres_emploi_brutes b ON e.offre_id = b.id
        WHERE b.posted_date >= CURRENT_DATE - INTERVAL '1 month'
        AND extracted_salary_min IS NOT NULL
        AND extracted_salary_max IS NOT NULL
        """
    ]
    
    try:
        for query in stats_queries:
            postgres_hook.run(query)
        
        logging.info("Statistiques mises à jour avec succès")
        
    except Exception as e:
        logging.error(f"Erreur lors de la mise à jour des statistiques: {e}")
        raise

# Définition des tâches Airflow
task_get_jobs = PythonOperator(
    task_id='get_jobs_to_process',
    python_callable=get_jobs_to_process,
    dag=dag,
)

task_process_nlp = PythonOperator(
    task_id='process_job_nlp',
    python_callable=process_job_nlp,
    dag=dag,
)

task_save_data = PythonOperator(
    task_id='save_enriched_data',
    python_callable=save_enriched_data,
    dag=dag,
)

task_update_stats = PythonOperator(
    task_id='update_job_statistics',
    python_callable=update_job_statistics,
    dag=dag,
)


# 🧹 1. Suppression des anciennes données
task_cleanup_delete = PostgresOperator(
    task_id='cleanup_old_data',
    sql="""
    DELETE FROM offres_emploi_brutes 
    WHERE posted_date < CURRENT_DATE - INTERVAL '2 years';
    """,
    conn_id='postgres_default',
    autocommit=False,
    dag=dag,
)

# 🧠 2. VACUUM séparé (autocommit obligatoire)
from airflow.operators.bash import BashOperator

task_vacuume = BashOperator(
    task_id='vacuum_analyze',
    bash_command="""
    psql "$AIRFLOW_CONN_POSTGRES_DEFAULT" -c "VACUUM ANALYZE offres_emploi_brutes;"
    psql "$AIRFLOW_CONN_POSTGRES_DEFAULT" -c "VACUUM ANALYZE offres_emploi_enrichies;"
    """,
    dag=dag,
)





# Dépendances
task_get_jobs >> task_process_nlp >> task_save_data >> task_update_stats >> task_cleanup_delete >> task_vacuume
