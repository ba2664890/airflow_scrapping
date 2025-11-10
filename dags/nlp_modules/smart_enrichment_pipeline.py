"""
Pipeline intelligent d'enrichissement des données d'offres d'emploi.
Utilise les offres complètes comme données d'entraînement et prédit
les champs manquants pour les autres offres.

Stratégie:
1. Séparer les offres en 2 groupes:
   - Complètes (toutes les colonnes remplies) → Train/Test
   - Incomplètes (valeurs manquantes) → À enrichir
2. Entraîner des modèles pour chaque champ manquant
3. Prédire les valeurs manquantes
4. Sauvegarder les résultats enrichis

Auteur: Emploi Dakar Analytics Team
"""

import os
import json
import logging
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from datetime import datetime

import torch
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, classification_report
from transformers import (
    AutoTokenizer, AutoModelForSequenceClassification,
    Trainer, TrainingArguments, EarlyStoppingCallback
)

# Imports des extracteurs existants
from .nlp_processor import NLPProcessor
from .skill_extractor import SkillExtractor
from .salary_extractor import SalaryExtractor
from .contract_classifier import ContractClassifier

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================

@dataclass
class EnrichmentConfig:
    """Configuration pour l'enrichissement."""
    
    # Modèles ML
    model_name: str = "camembert/camembert-base"
    num_epochs: int = 5
    batch_size: int = 16
    learning_rate: float = 2e-5
    max_length: int = 256
    
    # Chemins
    models_dir: str = "./models/enrichment"
    data_dir: str = "./data"
    output_dir: str = "./data/enriched"
    
    # Seuils
    min_confidence: float = 0.7  # Confiance minimum pour accepter une prédiction
    min_complete_samples: int = 50  # Minimum d'échantillons complets requis
    
    # Colonnes à enrichir (ordre de priorité)
    target_columns: List[str] = None
    
    def __post_init__(self):
        if self.target_columns is None:
            self.target_columns = [
                'extracted_sector',
                'extracted_contract_type',
                'job_level',
                'job_type',
                'extracted_skills',
                'extracted_salary_min',
                'extracted_salary_max'
            ]
        
        Path(self.models_dir).mkdir(parents=True, exist_ok=True)
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)


# ==================== DATASET PYTORCH ====================

class EnrichmentDataset(torch.utils.data.Dataset):
    """Dataset pour l'enrichissement."""
    
    def __init__(self, texts: List[str], labels: List[int], tokenizer, max_length: int = 256):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_length = max_length
    
    def __len__(self):
        return len(self.texts)
    
    def __getitem__(self, idx):
        text = str(self.texts[idx])
        label = self.labels[idx]
        
        encoding = self.tokenizer(
            text,
            add_special_tokens=True,
            max_length=self.max_length,
            padding='max_length',
            truncation=True,
            return_attention_mask=True,
            return_tensors='pt'
        )
        
        return {
            'input_ids': encoding['input_ids'].flatten(),
            'attention_mask': encoding['attention_mask'].flatten(),
            'labels': torch.tensor(label, dtype=torch.long)
        }


# ==================== ANALYSEUR DE DONNÉES ====================

class DataAnalyzer:
    """Analyse les données et identifie les colonnes à enrichir."""
    
    def __init__(self, config: EnrichmentConfig):
        self.config = config
    
    def analyze_dataframe(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyse le DataFrame et retourne des statistiques.
        
        Returns:
            Dict avec les stats de complétude par colonne
        """
        logger.info("📊 Analyse du DataFrame...")
        
        stats = {
            'total_rows': len(df),
            'columns_completeness': {},
            'complete_rows': 0,
            'incomplete_rows': 0
        }
        
        # Analyser chaque colonne cible
        for col in self.config.target_columns:
            if col not in df.columns:
                logger.warning(f"⚠️  Colonne '{col}' introuvable dans les données")
                continue
            
            non_null = df[col].notna().sum()
            null_count = df[col].isna().sum()
            completeness = (non_null / len(df)) * 100
            
            stats['columns_completeness'][col] = {
                'non_null': int(non_null),
                'null': int(null_count),
                'completeness': round(completeness, 2)
            }
            
            logger.info(f"  • {col}: {non_null}/{len(df)} ({completeness:.1f}%)")
        
        # Identifier les lignes complètes
        complete_mask = True
        for col in self.config.target_columns:
            if col in df.columns:
                complete_mask = complete_mask & df[col].notna()
        
        stats['complete_rows'] = int(complete_mask.sum())
        stats['incomplete_rows'] = int((~complete_mask).sum())
        
        logger.info(f"✅ Lignes complètes: {stats['complete_rows']}")
        logger.info(f"⚠️  Lignes incomplètes: {stats['incomplete_rows']}")
        
        return stats
    
    def split_complete_incomplete(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Sépare les données en complètes et incomplètes.
        
        Returns:
            (df_complete, df_incomplete)
        """
        logger.info("🔀 Séparation des données...")
        
        # Identifier les lignes complètes
        complete_mask = True
        for col in self.config.target_columns:
            if col in df.columns:
                complete_mask = complete_mask & df[col].notna()
        
        df_complete = df[complete_mask].copy()
        df_incomplete = df[~complete_mask].copy()
        
        logger.info(f"✅ {len(df_complete)} lignes complètes (train/test)")
        logger.info(f"🔧 {len(df_incomplete)} lignes à enrichir")
        
        if len(df_complete) < self.config.min_complete_samples:
            logger.warning(
                f"⚠️  Seulement {len(df_complete)} échantillons complets "
                f"(minimum recommandé: {self.config.min_complete_samples})"
            )
        
        return df_complete, df_incomplete


# ==================== ENRICHISSEUR PAR COLONNE ====================

class ColumnEnricher:
    """Enrichit une colonne spécifique en utilisant le ML."""
    
    def __init__(self, column_name: str, config: EnrichmentConfig):
        self.column_name = column_name
        self.config = config
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        self.label_encoder = {}
        self.reverse_label_encoder = {}
        self.tokenizer = None
        self.model = None
        self.trainer = None
        
        logger.info(f"🎯 Initialisation de l'enrichisseur pour: {column_name}")
    
    def prepare_data(self, df_train: pd.DataFrame) -> Tuple[List[str], List[int], int]:
        """
        Prépare les données d'entraînement.
        
        Returns:
            (texts, labels, num_labels)
        """
        logger.info(f"📋 Préparation des données pour {self.column_name}...")
        
        # Créer le texte d'entrée (title + description)
        texts = []
        for _, row in df_train.iterrows():
            text_parts = []
            if pd.notna(row.get('title')):
                text_parts.append(str(row['title']))
            if pd.notna(row.get('description')):
                text_parts.append(str(row['description']))
            
            text = ' '.join(text_parts)
            texts.append(text if text else "Aucune description")
        
        # Encoder les labels
        labels_raw = df_train[self.column_name].astype(str).tolist()
        unique_labels = sorted(set(labels_raw))
        
        self.label_encoder = {label: idx for idx, label in enumerate(unique_labels)}
        self.reverse_label_encoder = {idx: label for label, idx in self.label_encoder.items()}
        
        labels = [self.label_encoder[label] for label in labels_raw]
        num_labels = len(unique_labels)
        
        logger.info(f"  • {len(texts)} exemples")
        logger.info(f"  • {num_labels} classes: {unique_labels[:5]}...")
        
        return texts, labels, num_labels
    
    def train_model(self, X_train: List[str], y_train: List[int], 
                   X_val: List[str], y_val: List[int], num_labels: int):
        """Entraîne le modèle."""
        logger.info(f"🚀 Entraînement du modèle pour {self.column_name}...")
        
        # Charger tokenizer et modèle
        self.tokenizer = AutoTokenizer.from_pretrained(self.config.model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            self.config.model_name,
            num_labels=num_labels
        )
        self.model.to(self.device)
        
        # Créer les datasets
        train_dataset = EnrichmentDataset(X_train, y_train, self.tokenizer, self.config.max_length)
        val_dataset = EnrichmentDataset(X_val, y_val, self.tokenizer, self.config.max_length)
        
        # Configuration d'entraînement
        training_args = TrainingArguments(
            output_dir=f"{self.config.models_dir}/{self.column_name}",
            num_train_epochs=self.config.num_epochs,
            per_device_train_batch_size=self.config.batch_size,
            per_device_eval_batch_size=self.config.batch_size,
            learning_rate=self.config.learning_rate,
            evaluation_strategy="epoch",
            save_strategy="epoch",
            load_best_model_at_end=True,
            metric_for_best_model="f1",
            logging_steps=10,
            fp16=torch.cuda.is_available(),
            report_to="none"
        )
        
        # Métriques
        def compute_metrics(eval_pred):
            predictions, labels = eval_pred
            predictions = np.argmax(predictions, axis=1)
            acc = accuracy_score(labels, predictions)
            f1 = f1_score(labels, predictions, average='weighted', zero_division=0)
            return {'accuracy': acc, 'f1': f1}
        
        # Trainer
        self.trainer = Trainer(
            model=self.model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=val_dataset,
            compute_metrics=compute_metrics,
            callbacks=[EarlyStoppingCallback(early_stopping_patience=2)]
        )
        
        # Entraînement
        train_result = self.trainer.train()
        eval_result = self.trainer.evaluate()
        
        logger.info(f"✅ Entraînement terminé!")
        logger.info(f"  • Accuracy: {eval_result.get('eval_accuracy', 0):.2%}")
        logger.info(f"  • F1-Score: {eval_result.get('eval_f1', 0):.2%}")
        
        return eval_result
    
    def predict(self, texts: List[str]) -> List[Dict[str, Any]]:
        """
        Prédit les valeurs pour de nouveaux textes.
        
        Returns:
            Liste de dicts avec 'label' et 'confidence'
        """
        if not texts:
            return []
        
        logger.info(f"🔮 Prédiction de {len(texts)} valeurs pour {self.column_name}...")
        
        # Tokenization
        encodings = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=self.config.max_length,
            return_tensors='pt'
        )
        encodings = {k: v.to(self.device) for k, v in encodings.items()}
        
        # Prédiction
        self.model.eval()
        with torch.no_grad():
            outputs = self.model(**encodings)
            logits = outputs.logits
            probabilities = torch.softmax(logits, dim=1)
            predictions = torch.argmax(logits, dim=1)
        
        # Formater résultats
        results = []
        for i in range(len(texts)):
            pred_idx = predictions[i].item()
            pred_label = self.reverse_label_encoder[pred_idx]
            confidence = probabilities[i][pred_idx].item()
            
            results.append({
                'label': pred_label,
                'confidence': confidence,
                'accepted': confidence >= self.config.min_confidence
            })
        
        # Stats
        accepted = sum(1 for r in results if r['accepted'])
        logger.info(f"  • {accepted}/{len(results)} prédictions acceptées (confiance ≥ {self.config.min_confidence})")
        
        return results
    
    def save_model(self):
        """Sauvegarde le modèle."""
        save_path = f"{self.config.models_dir}/{self.column_name}"
        
        self.model.save_pretrained(save_path)
        self.tokenizer.save_pretrained(save_path)
        
        # Sauvegarder les encodeurs
        with open(f"{save_path}/label_encoder.json", 'w', encoding='utf-8') as f:
            json.dump({
                'label_encoder': self.label_encoder,
                'reverse_label_encoder': {int(k): v for k, v in self.reverse_label_encoder.items()}
            }, f, indent=2, ensure_ascii=False)
        
        logger.info(f"💾 Modèle sauvegardé: {save_path}")


# ==================== PIPELINE PRINCIPAL ====================

class SmartEnrichmentPipeline:
    """Pipeline complet d'enrichissement intelligent."""
    
    def __init__(self, config: EnrichmentConfig):
        self.config = config
        self.analyzer = DataAnalyzer(config)
        self.enrichers = {}
        
        # Extracteurs classiques (fallback)
        self.nlp_processor = NLPProcessor()
        self.skill_extractor = SkillExtractor()
        self.salary_extractor = SalaryExtractor()
        self.contract_classifier = ContractClassifier()
    
    def load_data(self, filepath: str) -> pd.DataFrame:
        """Charge les données depuis un fichier."""
        logger.info(f"📂 Chargement des données: {filepath}")
        
        if filepath.endswith('.csv'):
            df = pd.read_csv(filepath)
        elif filepath.endswith('.json'):
            df = pd.read_json(filepath)
        elif filepath.endswith('.parquet'):
            df = pd.read_parquet(filepath)
        else:
            raise ValueError(f"Format non supporté: {filepath}")
        
        logger.info(f"✅ {len(df)} lignes chargées")
        return df
    
    def enrich_column_ml(self, column_name: str, df_complete: pd.DataFrame, 
                        df_incomplete: pd.DataFrame) -> pd.Series:
        """
        Enrichit une colonne avec le ML.
        
        Returns:
            Series avec les valeurs prédites (index = df_incomplete.index)
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"🎯 ENRICHISSEMENT ML: {column_name}")
        logger.info(f"{'='*60}")
        
        # Créer l'enrichisseur
        enricher = ColumnEnricher(column_name, self.config)
        
        # Préparer les données
        texts, labels, num_labels = enricher.prepare_data(df_complete)
        
        # Split train/val
        X_train, X_val, y_train, y_val = train_test_split(
            texts, labels,
            test_size=0.2,
            random_state=42,
            stratify=labels
        )
        
        logger.info(f"📊 Split: {len(X_train)} train, {len(X_val)} validation")
        
        # Entraîner
        enricher.train_model(X_train, y_train, X_val, y_val, num_labels)
        
        # Sauvegarder le modèle
        enricher.save_model()
        self.enrichers[column_name] = enricher
        
        # Prédire sur les données incomplètes
        texts_to_predict = []
        for _, row in df_incomplete.iterrows():
            text_parts = []
            if pd.notna(row.get('title')):
                text_parts.append(str(row['title']))
            if pd.notna(row.get('description')):
                text_parts.append(str(row['description']))
            
            texts_to_predict.append(' '.join(text_parts) if text_parts else "Aucune description")
        
        predictions = enricher.predict(texts_to_predict)
        
        # Créer la série de résultats
        predicted_values = []
        for pred in predictions:
            if pred['accepted']:
                predicted_values.append(pred['label'])
            else:
                predicted_values.append(None)  # Confiance trop faible
        
        return pd.Series(predicted_values, index=df_incomplete.index)
    
    def enrich_skills_classical(self, df_incomplete: pd.DataFrame) -> pd.Series:
        """Enrichit les skills avec l'extracteur classique."""
        logger.info(f"\n🔧 Enrichissement classique: extracted_skills")
        
        skills_list = []
        for _, row in df_incomplete.iterrows():
            text = f"{row.get('title', '')} {row.get('description', '')}"
            skills = self.skill_extractor.extract_skills(text)
            skills_list.append(skills if skills else None)
        
        logger.info(f"  • {sum(1 for s in skills_list if s)}/{len(skills_list)} valeurs extraites")
        
        return pd.Series(skills_list, index=df_incomplete.index)
    
    def enrich_salary_classical(self, df_incomplete: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """Enrichit les salaires avec l'extracteur classique."""
        logger.info(f"\n🔧 Enrichissement classique: salaires")
        
        min_salaries = []
        max_salaries = []
        
        for _, row in df_incomplete.iterrows():
            text = f"{row.get('title', '')} {row.get('description', '')}"
            salary_info = self.salary_extractor.extract_salary(text)
            
            min_salaries.append(salary_info.get('min_salary'))
            max_salaries.append(salary_info.get('max_salary'))
        
        extracted = sum(1 for s in min_salaries if s is not None)
        logger.info(f"  • {extracted}/{len(min_salaries)} salaires extraits")
        
        return (
            pd.Series(min_salaries, index=df_incomplete.index),
            pd.Series(max_salaries, index=df_incomplete.index)
        )
    
    def run_full_enrichment(self, input_filepath: str, output_filepath: Optional[str] = None):
        """
        Execute le pipeline complet d'enrichissement.
        
        Args:
            input_filepath: Chemin vers les données brutes
            output_filepath: Chemin de sortie (optionnel)
        """
        logger.info("\n" + "="*80)
        logger.info("🚀 DÉMARRAGE DU PIPELINE D'ENRICHISSEMENT INTELLIGENT")
        logger.info("="*80 + "\n")
        
        # 1. Charger les données
        df = self.load_data(input_filepath)
        
        # 2. Analyser
        stats = self.analyzer.analyze_dataframe(df)
        
        # 3. Séparer complètes/incomplètes
        df_complete, df_incomplete = self.analyzer.split_complete_incomplete(df)
        
        if len(df_complete) < self.config.min_complete_samples:
            logger.error(
                f"❌ Pas assez d'échantillons complets ({len(df_complete)} < {self.config.min_complete_samples})"
            )
            logger.info("💡 Utilisation uniquement des extracteurs classiques")
            use_ml = False
        else:
            use_ml = True
        
        # 4. Enrichir chaque colonne
        enrichment_results = {}
        
        for col in self.config.target_columns:
            if col not in df.columns:
                continue
            
            # Vérifier si la colonne a besoin d'enrichissement
            if df_incomplete[col].isna().sum() == 0:
                logger.info(f"✅ {col}: Déjà complet, skip")
                continue
            
            try:
                if use_ml and col in ['extracted_sector', 'extracted_contract_type', 'job_level', 'job_type']:
                    # Enrichissement ML
                    enrichment_results[col] = self.enrich_column_ml(col, df_complete, df_incomplete)
                
                elif col == 'extracted_skills':
                    # Extracteur classique pour les skills
                    enrichment_results[col] = self.enrich_skills_classical(df_incomplete)
                
                elif col in ['extracted_salary_min', 'extracted_salary_max']:
                    # Extracteur classique pour les salaires
                    if 'extracted_salary_min' not in enrichment_results:
                        min_sal, max_sal = self.enrich_salary_classical(df_incomplete)
                        enrichment_results['extracted_salary_min'] = min_sal
                        enrichment_results['extracted_salary_max'] = max_sal
                
            except Exception as e:
                logger.error(f"❌ Erreur lors de l'enrichissement de {col}: {e}")
                continue
        
        # 5. Appliquer les enrichissements
        logger.info(f"\n{'='*60}")
        logger.info("📝 APPLICATION DES ENRICHISSEMENTS")
        logger.info(f"{'='*60}")
        
        df_enriched = df.copy()
        
        for col, predictions in enrichment_results.items():
            # Remplir uniquement les valeurs manquantes
            mask = df_enriched[col].isna()
            df_enriched.loc[mask, col] = predictions
            
            filled = df_enriched[col].notna().sum()
            total = len(df_enriched)
            logger.info(f"  • {col}: {filled}/{total} ({filled/total*100:.1f}%) complétés")
        
        # 6. Sauvegarder
        if output_filepath is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filepath = f"{self.config.output_dir}/enriched_data_{timestamp}.csv"
        
        df_enriched.to_csv(output_filepath, index=False)
        logger.info(f"\n💾 Données enrichies sauvegardées: {output_filepath}")
        
        # 7. Rapport final
        logger.info(f"\n{'='*80}")
        logger.info("✅ ENRICHISSEMENT TERMINÉ")
        logger.info(f"{'='*80}")
        logger.info(f"📊 Lignes totales: {len(df_enriched)}")
        logger.info(f"🎯 Colonnes enrichies: {len(enrichment_results)}")
        
        # Stats avant/après
        logger.info(f"\n📈 COMPARAISON AVANT/APRÈS:")
        for col in self.config.target_columns:
            if col in df.columns:
                before = df[col].notna().sum()
                after = df_enriched[col].notna().sum()
                improvement = after - before
                logger.info(f"  • {col}: {before} → {after} (+{improvement})")
        
        return df_enriched


# ==================== FONCTION PRINCIPALE ====================

def main():
    """Fonction principale."""
    
    print("\n" + "="*80)
    print("🚀 PIPELINE D'ENRICHISSEMENT INTELLIGENT DES DONNÉES")
    print("="*80 + "\n")
    
    # Configuration
    config = EnrichmentConfig(
        model_name="camembert/camembert-base",
        num_epochs=3,
        batch_size=16,
        min_confidence=0.70,
        min_complete_samples=50
    )
    
    # Créer le pipeline
    pipeline = SmartEnrichmentPipeline(config)
    
    # Exemple: Charger depuis la base de données
    # df = pipeline.load_data("./data/offres_brutes.csv")
    
    # Ou créer des données de test
    print("📦 Création de données de test...")
    df_test = create_test_data()
    df_test.to_csv("./data/test_offers.csv", index=False)
    
    # Lancer l'enrichissement
    df_enriched = pipeline.run_full_enrichment(
        input_filepath="./data/test_offers.csv",
        output_filepath="./data/enriched_offers.csv"
    )
    
    print("\n✅ Pipeline terminé avec succès!")


def create_test_data() -> pd.DataFrame:
    """Crée des données de test."""
    
    data = []
    
    # Données complètes (pour training)
    complete_samples = [
        {
            'title': 'Développeur Python Senior',
            'description': 'Recherche développeur Python avec 5 ans d\'expérience en Django et FastAPI. CDI. Salaire 800K-1.2M FCFA.',
            'extracted_sector': 'IT/Tech',
            'extracted_contract_type': 'CDI',
            'job_level': 'Senior',
            'job_type': 'Full-time',
            'extracted_skills': ['Python', 'Django', 'FastAPI']
        },
        {
            'title': 'Comptable confirmé',
            'description': 'Cabinet recherche comptable confirmé. CDI. Expérience 3 ans minimum. Salaire 400K-600K FCFA.',
            'extracted_sector': 'Finance',
            'extracted_contract_type': 'CDI',
            'job_level': 'Confirmé',
            'job_type': 'Full-time',
            'extracted_skills': ['Comptabilité', 'Excel']
        },
        # ... (ajouter plus d'exemples complets)
    ] * 25  # Répéter pour avoir 50+ échantillons
    
    # Données incomplètes (à enrichir)
    incomplete_samples = [
        {
            'title': 'Ingénieur DevOps',
            'description': 'Poste d\'ingénieur DevOps pour gérer infrastructure cloud AWS et Kubernetes',
            'extracted_sector': None,
            'extracted_contract_type': None,
            'job_level': None,
            'job_type': None,
            'extracted_skills': None
        },
        {
            'title': 'Chef de projet marketing',
            'description': 'Recherche chef de projet marketing digital avec expérience e-commerce',
            'extracted_sector': None,
            'extracted_contract_type': None,
            'job_level': None,
            'job_type': None,
            'extracted_skills': None
        },
        # ... (ajouter plus d'exemples incomplets)
    ] * 20
    
    data = complete_samples + incomplete_samples
    
    return pd.DataFrame(data)


if __name__ == "__main__":
    main()