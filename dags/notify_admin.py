"""
DAG Airflow pour les notifications d'administration.
Ce DAG envoie des rapports par email, Slack ou Discord sur l'état du pipeline.
"""

import os
import logging
import requests
import json
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.email import EmailOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator

# -------------------------
# CONFIGURATION DU DAG
# -------------------------
default_args = {
    'owner': 'admin-team',
    'depends_on_past': False,
    'start_date': datetime.now() - timedelta(days=1),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'notify_admin',
    default_args=default_args,
    description="Notifications d'administration pour le pipeline ETL",
    schedule='0 6 * * *',  # Airflow 3.x → 'schedule' au lieu de 'schedule_interval'
    catchup=False,
    tags=['notifications', 'admin', 'monitoring'],
)

# -------------------------
# 1️⃣ GÉNÉRATION DU RAPPORT
# -------------------------
def generate_daily_report(**context):
    logging.info("Génération du rapport quotidien")
    postgres_hook = PostgresHook(postgres_conn_id='neon_conn')

    stats_queries = {
        'total_offers': "SELECT COUNT(*) FROM offres_emploi_brutes",
        'new_offers_today': "SELECT COUNT(*) FROM offres_emploi_brutes WHERE created_at >= CURRENT_DATE",
        'enriched_offers': "SELECT COUNT(*) FROM offres_emploi_enrichies",
        'new_enriched_today': "SELECT COUNT(*) FROM offres_emploi_enrichies WHERE processed_at >= CURRENT_DATE",
        'avg_salary_range': """
            SELECT AVG(extracted_salary_min), AVG(extracted_salary_max)
            FROM offres_emploi_enrichies 
            WHERE extracted_salary_min IS NOT NULL
        """,
        'top_sectors': """
            SELECT extracted_sector, COUNT(*) 
            FROM offres_emploi_enrichies e
            JOIN offres_emploi_brutes b ON e.offre_id = b.id
            WHERE b.posted_date >= CURRENT_DATE - INTERVAL '7 days'
            AND extracted_sector IS NOT NULL
            GROUP BY extracted_sector
            ORDER BY COUNT(*) DESC
            LIMIT 5
        """,
        'top_skills': """
            SELECT skill, COUNT(*) 
            FROM (
                SELECT unnest(extracted_skills) as skill
                FROM offres_emploi_enrichies e
                JOIN offres_emploi_brutes b ON e.offre_id = b.id
                WHERE b.posted_date >= CURRENT_DATE - INTERVAL '7 days'
                AND extracted_skills IS NOT NULL
            ) as s
            GROUP BY skill
            ORDER BY COUNT(*) DESC
            LIMIT 10
        """,
    }

    report_data = {}
    for key, query in stats_queries.items():
        try:
            result = postgres_hook.get_records(query)
            report_data[key] = result
        except Exception as e:
            logging.error(f"Erreur pour {key}: {e}")
            report_data[key] = []

    report = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'summary': {
            'total_offers': report_data.get('total_offers', [[0]])[0][0],
            'new_offers_today': report_data.get('new_offers_today', [[0]])[0][0],
            'total_enriched': report_data.get('enriched_offers', [[0]])[0][0],
            'new_enriched_today': report_data.get('new_enriched_today', [[0]])[0][0],
        },
        'salary_info': {
            'avg_min_salary': float(report_data.get('avg_salary_range', [[0, 0]])[0][0] or 0),
            'avg_max_salary': float(report_data.get('avg_salary_range', [[0, 0]])[0][1] or 0),
        },
        'top_sectors': [{'sector': r[0], 'count': r[1]} for r in report_data.get('top_sectors', [])],
        'top_skills': [{'skill': r[0], 'count': r[1]} for r in report_data.get('top_skills', [])],
    }
    report_json = json.dumps(report)
    ti = context['task_instance']          # ← récupération
    ti.xcom_push(key='daily_report', value=report_json)
    return report_json          # optionnel, mais OK pour logs

 

# -------------------------
# 2️⃣ FORMATAGE EMAIL HTML
# -------------------------
def build_email_html(**context):
    import json
    report_json = context['task_instance'].xcom_pull(
        key='daily_report',
        task_ids='generate_daily_report'
    )
    if not report_json:
        return "<p>Aucune donnée disponible pour le rapport du jour.</p>"

    report_data = json.loads(report_json)   # ← décodage

    html = f"""
    <h2>📊 Rapport Quotidien - {report_data['date']}</h2>
    <p><b>Total offres:</b> {report_data['summary']['total_offers']}</p>
    <p><b>Nouvelles offres:</b> {report_data['summary']['new_offers_today']}</p>
    <p><b>Offres enrichies:</b> {report_data['summary']['total_enriched']}</p>
    <p><b>Nouvelles enrichies:</b> {report_data['summary']['new_enriched_today']}</p>
    <p><b>Salaire moyen min:</b> {report_data['salary_info']['avg_min_salary']:.0f} XOF</p>
    <p><b>Salaire moyen max:</b> {report_data['salary_info']['avg_max_salary']:.0f} XOF</p>
    """
    return html


# -------------------------
# 3️⃣ SLACK & DISCORD
# -------------------------
def send_slack_notification(**context):
    report = context['task_instance'].xcom_pull(key='daily_report', task_ids='generate_daily_report')
    if not report:
        logging.warning("Aucun rapport trouvé pour Slack")
        return

    slack_webhook = os.getenv('SLACK_WEBHOOK_URL')
    if not slack_webhook:
        logging.warning("SLACK_WEBHOOK_URL non défini")
        return

    payload = {
        "text": f"📊 Rapport Emploi Dakar {report['date']}\n"
                f"Total: {report['summary']['total_offers']}, "
                f"Nouvelles: {report['summary']['new_offers_today']}, "
                f"Enrichies: {report['summary']['total_enriched']}"
    }
    requests.post(slack_webhook, json=payload)


def send_discord_notification(**context):
    report = context['task_instance'].xcom_pull(key='daily_report', task_ids='generate_daily_report')
    if not report:
        logging.warning("Aucun rapport trouvé pour Discord")
        return

    discord_webhook = os.getenv('DISCORD_WEBHOOK_URL')
    if not discord_webhook:
        logging.warning("DISCORD_WEBHOOK_URL non défini")
        return

    embed = {
        "title": f"📊 Rapport Emploi Dakar - {report['date']}",
        "fields": [
            {"name": "Total Offres", "value": str(report['summary']['total_offers']), "inline": True},
            {"name": "Nouvelles Offres", "value": str(report['summary']['new_offers_today']), "inline": True},
        ],
        "color": 3447003,
    }

    requests.post(discord_webhook, json={"embeds": [embed]})


# -------------------------
# 4️⃣ TÂCHES AIRFLOW
# -------------------------
task_generate_report = PythonOperator(
    task_id='generate_daily_report',
    python_callable=generate_daily_report,
    dag=dag,
)

task_build_email = PythonOperator(
    task_id='build_email_html',
    python_callable=build_email_html,
    dag=dag,
)

task_send_email = EmailOperator(
    task_id='send_email_report',
    to=None,
    subject='📊 Rapport Quotidien - Plateforme Emploi Dakar',
    html_content="{{ task_instance.xcom_pull(task_ids='build_email_html') }}",
    dag=dag,
)

task_send_slack = PythonOperator(
    task_id='send_slack_notification',
    python_callable=send_slack_notification,
    dag=dag,
)

task_send_discord = PythonOperator(
    task_id='send_discord_notification',
    python_callable=send_discord_notification,
    dag=dag,
)

task_save_report = SQLExecuteQueryOperator(
    task_id='save_daily_report',
    conn_id='postgres_default',
    sql="""
        INSERT INTO job_statistics (id, metric_name, metric_value, period_start, period_end, category)
        VALUES (
            uuid_generate_v4(),
            'daily_summary_report',
            %(report)s::jsonb,
            CURRENT_DATE,
            CURRENT_DATE,
            'admin_report'
        );
    """,
    parameters={
        "report": "{{ task_instance.xcom_pull(key='daily_report', task_ids='generate_daily_report') }}"
    },
    dag=dag,
)

# -------------------------
# 5️⃣ DÉPENDANCES
# -------------------------
task_generate_report >> task_build_email >> task_send_email
task_generate_report >> [task_send_slack, task_send_discord, task_save_report]
