"""
Script d'intégration pour enrichir automatiquement les offres d'emploi
depuis la base de données PostgreSQL.

Workflow:
1. Extraire les offres de la BDD
2. Identifier les complètes vs incomplètes
3. Entraîner sur les complètes
4. Prédire sur les incomplètes
5. Mettre à jour la BDD

Usage:
    python enrich_database.py --mode train    # Entraîner les modèles
    python enrich_database.py --mode predict  # Enrichir les données
    python enrich_database.py --mode full     # Train + Predict
"""

import sys
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.models.database_models import OffreEmploiEnrichie

# Imports des modèles et services
sys.path.append(str(Path(__file__).parent.parent))
#from app.database import get_db, engine
from nlp_modules.nlp_processor import NLPProcessor
from nlp_modules.skill_extractor import SkillExtractor
from nlp_modules.salary_extractor import SalaryExtractor
from nlp_modules.contract_classifier import ContractClassifier

# Import du pipeline d'enrichissement
from nlp_modules.smart_enrichment_pipeline import SmartEnrichmentPipeline, EnrichmentConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ==================== EXTRACTEUR DE DONNÉES ====================

class DatabaseExtractor:
    """Extrait les données de la base de données."""
    
    def __init__(self, db_url: str):
        self.engine = create_engine(db_url)
        self.Session = sessionmaker(bind=self.engine)
    
    def extract_all_offers(self) -> pd.DataFrame:
        """
        Extrait toutes les offres avec leurs enrichissements.
        
        Returns:
            DataFrame avec colonnes: id, title, description, extracted_*
        """
        logger.info("📂 Extraction des offres depuis la BDD...")
        
        query = """
        SELECT 
            b.id,
            b.title,
            b.description,
            b.company_name,
            b.location,
            b.posted_date,
            e.extracted_sector,
            e.extracted_contract_type,
            e.extracted_skills,
            e.extracted_salary_min,
            e.extracted_salary_max,
            e.job_level,
            e.job_type,
            e.confidence_score
        FROM offres_emploi_brutes b
        LEFT JOIN offres_emploi_enrichies e ON b.id = e.offre_id
        WHERE b.description IS NOT NULL
        ORDER BY b.created_at DESC
        """
        
        df = pd.read_sql(query, self.engine)
        logger.info(f"✅ {len(df)} offres extraites")
        
        return df
    
    def get_completeness_stats(self, df: pd.DataFrame) -> Dict:
        """Calcule les stats de complétude."""
        stats = {
            'total': len(df),
            'with_enrichment': df['extracted_sector'].notna().sum(),
            'without_enrichment': df['extracted_sector'].isna().sum()
        }
        
        logger.info(f"📊 Stats:")
        logger.info(f"  • Total: {stats['total']}")
        logger.info(f"  • Avec enrichissement: {stats['with_enrichment']}")
        logger.info(f"  • Sans enrichissement: {stats['without_enrichment']}")
        
        return stats


# ==================== MISE À JOUR DE LA BDD ====================

class DatabaseUpdater:
    """Met à jour les enrichissements dans la BDD."""
    
    def __init__(self, db_url: str):
        self.engine = create_engine(db_url)
        self.Session = sessionmaker(bind=self.engine)
    
    def update_enrichments(self, df_enriched: pd.DataFrame, batch_size: int = 100):
        """
        Met à jour les enrichissements dans la BDD.
        
        Args:
            df_enriched: DataFrame avec les prédictions
            batch_size: Taille des batchs pour l'update
        """
        logger.info(f"💾 Mise à jour de {len(df_enriched)} enrichissements...")
        
        session = self.Session()
        updated_count = 0
        created_count = 0
        
        try:
            for idx, row in df_enriched.iterrows():
                if pd.isna(row['id']):
                    continue
                
                offer_id = row['id']
                
                # Vérifier si l'enrichissement existe
                enrichie = session.query(OffreEmploiEnrichie).filter_by(offre_id=offer_id).first()
                
                if enrichie:
                    # Mettre à jour
                    if pd.notna(row['extracted_sector']):
                        enrichie.extracted_sector = row['extracted_sector']
                    if pd.notna(row['extracted_contract_type']):
                        enrichie.extracted_contract_type = row['extracted_contract_type']
                    if pd.notna(row['job_level']):
                        enrichie.job_level = row['job_level']
                    if pd.notna(row['job_type']):
                        enrichie.job_type = row['job_type']
                    if pd.notna(row['extracted_skills']):
                        # Convertir la liste en array PostgreSQL
                        if isinstance(row['extracted_skills'], list):
                            enrichie.extracted_skills = row['extracted_skills']
                    if pd.notna(row['extracted_salary_min']):
                        enrichie.extracted_salary_min = int(row['extracted_salary_min'])
                    if pd.notna(row['extracted_salary_max']):
                        enrichie.extracted_salary_max = int(row['extracted_salary_max'])
                    
                    enrichie.processed_at = datetime.utcnow()
                    updated_count += 1
                else:
                    # Créer
                    new_enrichie = OffreEmploiEnrichie(
                        offre_id=offer_id,
                        extracted_sector=row.get('extracted_sector') if pd.notna(row.get('extracted_sector')) else None,
                        extracted_contract_type=row.get('extracted_contract_type') if pd.notna(row.get('extracted_contract_type')) else None,
                        job_level=row.get('job_level') if pd.notna(row.get('job_level')) else None,
                        job_type=row.get('job_type') if pd.notna(row.get('job_type')) else None,
                        extracted_skills=row.get('extracted_skills') if pd.notna(row.get('extracted_skills')) else None,
                        extracted_salary_min=int(row['extracted_salary_min']) if pd.notna(row.get('extracted_salary_min')) else None,
                        extracted_salary_max=int(row['extracted_salary_max']) if pd.notna(row.get('extracted_salary_max')) else None,
                        processing_version='1.0',
                        processed_at=datetime.utcnow()
                    )
                    session.add(new_enrichie)
                    created_count += 1
                
                # Commit par batch
                if (idx + 1) % batch_size == 0:
                    session.commit()
                    logger.info(f"  • Batch {(idx + 1) // batch_size}: {batch_size} lignes")
            
            # Commit final
            session.commit()
            
            logger.info(f"✅ Mise à jour terminée:")
            logger.info(f"  • {updated_count} mises à jour")
            logger.info(f"  • {created_count} créations")
            
        except Exception as e:
            session.rollback()
            logger.error(f"❌ Erreur lors de la mise à jour: {e}")
            raise
        finally:
            session.close()


# ==================== PIPELINE COMPLET ====================

class DatabaseEnrichmentPipeline:
    """Pipeline complet d'enrichissement depuis la BDD."""
    
    def __init__(self, db_url: str, config: EnrichmentConfig):
        self.db_url = db_url
        self.config = config
        self.extractor = DatabaseExtractor(db_url)
        self.updater = DatabaseUpdater(db_url)
        self.enrichment_pipeline = SmartEnrichmentPipeline(config)
    
    def run_training(self):
        """Entraîne les modèles sur les données complètes."""
        logger.info("\n" + "="*80)
        logger.info("🎓 MODE ENTRAÎNEMENT")
        logger.info("="*80 + "\n")
        
        # Extraire les données
        df = self.extractor.extract_all_offers()
        
        # Sauvegarder temporairement
        temp_file = f"{self.config.data_dir}/temp_training_data.csv"
        df.to_csv(temp_file, index=False)
        
        # Séparer complètes/incomplètes
        df_complete, df_incomplete = self.enrichment_pipeline.analyzer.split_complete_incomplete(df)
        
        if len(df_complete) < self.config.min_complete_samples:
            logger.error(f"❌ Pas assez de données complètes: {len(df_complete)}")
            logger.error(f"   Minimum requis: {self.config.min_complete_samples}")
            return False
        
        # Entraîner pour chaque colonne
        for col in self.config.target_columns:
            if col not in df.columns:
                continue
            
            if col in ['extracted_sector', 'extracted_contract_type', 'job_level', 'job_type']:
                try:
                    logger.info(f"\n🎯 Entraînement du modèle pour: {col}")
                    self.enrichment_pipeline.enrich_column_ml(col, df_complete, df_incomplete[:1])  # Dummy predict
                    logger.info(f"✅ Modèle {col} entraîné et sauvegardé")
                except Exception as e:
                    logger.error(f"❌ Erreur pour {col}: {e}")
        
        logger.info("\n✅ Entraînement terminé!")
        return True
    
    def run_prediction(self):
        """Prédit et met à jour les données incomplètes."""
        logger.info("\n" + "="*80)
        logger.info("🔮 MODE PRÉDICTION")
        logger.info("="*80 + "\n")
        
        # Extraire les données
        df = self.extractor.extract_all_offers()
        
        # Identifier les offres à enrichir (sans extracted_sector)
        df_to_enrich = df[df['extracted_sector'].isna()].copy()
        
        if len(df_to_enrich) == 0:
            logger.info("✅ Toutes les offres sont déjà enrichies!")
            return
        
        logger.info(f"🔧 {len(df_to_enrich)} offres à enrichir")
        
        # Charger les modèles et prédire
        enriched_data = {}
        
        for col in self.config.target_columns:
            model_path = f"{self.config.models_dir}/{col}"
            
            if not Path(model_path).exists():
                logger.warning(f"⚠️  Modèle introuvable pour {col}, skip")
                continue
            
            try:
                logger.info(f"\n🔮 Prédiction pour: {col}")
                
                # Charger le modèle
                # importer l'enricher depuis le package nlp_modules
                from nlp_modules.smart_enrichment_pipeline import ColumnEnricher
                enricher = ColumnEnricher(col, self.config)
                
                # Charger le tokenizer et le modèle (transformers)
                from transformers import AutoTokenizer, AutoModelForSequenceClassification
                import json
                
                enricher.tokenizer = AutoTokenizer.from_pretrained(model_path)
                enricher.model = AutoModelForSequenceClassification.from_pretrained(model_path)
                enricher.model.to(enricher.device)
                
                with open(f"{model_path}/label_encoder.json", 'r') as f:
                    label_info = json.load(f)
                enricher.label_encoder = label_info['label_encoder']
                enricher.reverse_label_encoder = {int(k): v for k, v in label_info['reverse_label_encoder'].items()}
                
                # Préparer les textes
                texts = []
                for _, row in df_to_enrich.iterrows():
                    text = f"{row.get('title', '')} {row.get('description', '')}"
                    texts.append(text)
                
                # Prédire
                predictions = enricher.predict(texts)
                
                # Stocker
                enriched_data[col] = [p['label'] if p['accepted'] else None for p in predictions]
                
            except Exception as e:
                logger.error(f"❌ Erreur pour {col}: {e}")
        
        # Enrichissement classique pour skills et salaires
        logger.info("\n🔧 Enrichissement classique...")
        
        # Skills
        skill_extractor = SkillExtractor()
        skills_list = []
        for _, row in df_to_enrich.iterrows():
            text = f"{row.get('title', '')} {row.get('description', '')}"
            skills = skill_extractor.extract_skills(text)
            skills_list.append(skills if skills else None)
        enriched_data['extracted_skills'] = skills_list
        
        # Salaires
        salary_extractor = SalaryExtractor()
        min_salaries = []
        max_salaries = []
        for _, row in df_to_enrich.iterrows():
            text = f"{row.get('title', '')} {row.get('description', '')}"
            salary_info = salary_extractor.extract_salary(text)
            min_salaries.append(salary_info.get('min_salary'))
            max_salaries.append(salary_info.get('max_salary'))
        enriched_data['extracted_salary_min'] = min_salaries
        enriched_data['extracted_salary_max'] = max_salaries
        
        # Créer le DataFrame enrichi
        df_enriched = df_to_enrich.copy()
        for col, values in enriched_data.items():
            df_enriched[col] = values
        
        # Mettre à jour la BDD
        self.updater.update_enrichments(df_enriched)
        
        logger.info("\n✅ Prédiction et mise à jour terminées!")
    
    def run_full_pipeline(self):
        """Exécute le pipeline complet: entraînement + prédiction."""
        logger.info("\n" + "="*80)
        logger.info("🚀 PIPELINE COMPLET D'ENRICHISSEMENT")
        logger.info("="*80 + "\n")
        
        # 1. Entraînement
        success = self.run_training()
        
        if not success:
            logger.error("❌ Échec de l'entraînement, arrêt du pipeline")
            return
        
        # 2. Prédiction
        self.run_prediction()
        
        logger.info("\n" + "="*80)
        logger.info("✅ PIPELINE COMPLET TERMINÉ AVEC SUCCÈS!")
        logger.info("="*80)


# ==================== CLI ====================

def main():
    parser = argparse.ArgumentParser(description="Enrichissement automatique des offres d'emploi")
    parser.add_argument(
        '--mode',
        choices=['train', 'predict', 'full'],
        default='full',
        help='Mode d\'exécution (train, predict, ou full)'
    )
    parser.add_argument(
        '--db-url',
        default=None,
        help='URL de connexion à la BDD (défaut: depuis les variables d\'environnement)'
    )
    parser.add_argument(
        '--min-confidence',
        type=float,
        default=0.70,
        help='Confiance minimum pour accepter une prédiction (défaut: 0.70)'
    )
    parser.add_argument(
        '--epochs',
        type=int,
        default=3,
        help='Nombre d\'epochs d\'entraînement (défaut: 3)'
    )
    
    args = parser.parse_args()
    
    # Configuration
    db_url = args.db_url or os.getenv('DATABASE_URL', 'postgresql://user:password@localhost/emploi_dakar')
    
    config = EnrichmentConfig(
        model_name="camembert/camembert-base",
        num_epochs=args.epochs,
        batch_size=16,
        min_confidence=args.min_confidence,
        min_complete_samples=50
    )
    
    # Pipeline
    pipeline = DatabaseEnrichmentPipeline(db_url, config)
    
    # Exécution selon le mode
    if args.mode == 'train':
        pipeline.run_training()
    elif args.mode == 'predict':
        pipeline.run_prediction()
    elif args.mode == 'full':
        pipeline.run_full_pipeline()


if __name__ == "__main__":
    import os
    main()