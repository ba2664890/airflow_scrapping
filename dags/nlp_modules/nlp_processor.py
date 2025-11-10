"""
Processeur NLP principal pour l'analyse sémantique des offres d'emploi.
Utilise des modèles de langage français pour l'extraction d'informations.
"""

import re
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

import spacy

@dataclass
class NLPResults:
    """Structure pour stocker les résultats du traitement NLP."""
    experience_years: Optional[int] = None
    sector: Optional[str] = None
    job_category: Optional[str] = None
    job_level: Optional[str] = None
    job_type: Optional[str] = None
    sentiment_score: Optional[float] = None
    key_phrases: List[str] = field(default_factory=list)
    confidence_score: Optional[float] = None

class NLPProcessor:
    """
    Processeur NLP pour l'analyse des offres d'emploi en français.
    """
    
    def __init__(self, model_name: str = "fr_core_news_sm"):
        """
        Initialise le processeur NLP.
        
        Args:
            model_name: Nom du modèle spaCy français
        """
        try:
            self.nlp = spacy.load(model_name)
            logging.info(f"Modèle spaCy '{model_name}' chargé avec succès")
        except OSError:
            logging.warning(f"Modèle spaCy '{model_name}' non trouvé, utilisation du modèle de base")
            self.nlp = None
        
        # Patterns pour l'extraction d'informations
        self.experience_patterns = [
            r'(\d+)\s*(?:an|ans|année|années)\s*(?:d\'expérience|expérience)',
            r'expérience\s*(?:de\s*)?(\d+)\s*(?:an|ans|année|années)',
            r'(\d+)\+?\s*(?:an|ans|année|années)',
        ]
        
        self.job_level_keywords = {
            'Junior': ['junior', 'débutant', 'entry level', 'stagiaire', 'alternant'],
            'Senior': ['senior', 'expérimenté', 'confirmé', 'lead'],
            'Lead': ['lead', 'chef', 'manager', 'directeur', 'responsable'],
            'Expert': ['expert', 'spécialiste', 'consultant senior']
        }
        
        self.job_type_keywords = {
            'Full-time': ['temps plein', 'full time', 'cdi', 'contrat à durée indéterminée'],
            'Part-time': ['temps partiel', 'part time'],
            'Contract': ['cdd', 'contrat à durée déterminée', 'freelance', 'consultant'],
            'Internship': ['stage', 'stagiaire', 'alternance'],
            'Remote': ['télétravail', 'remote', 'à distance', 'home office']
        }
        
        self.sector_keywords = {
            'IT/Tech': ['informatique', 'technologie', 'développeur', 'programmeur', 'software', 'web', 'mobile', 'data'],
            'Finance': ['finance', 'comptabilité', 'banque', 'audit', 'comptable'],
            'Marketing': ['marketing', 'communication', 'publicité', 'digital marketing'],
            'Sales': ['vente', 'commercial', 'sales', 'business development'],
            'HR': ['ressources humaines', 'rh', 'recrutement', 'hr'],
            'Engineering': ['ingénieur', 'engineering', 'civil', 'mécanique', 'électrique'],
            'Healthcare': ['santé', 'médical', 'infirmier', 'docteur', 'pharmacie'],
            'Education': ['éducation', 'enseignant', 'professeur', 'formation'],
            'Logistics': ['logistique', 'supply chain', 'transport', 'warehouse'],
            'Customer Service': ['service client', 'customer service', 'support client']
        }
    
    def process_text(self, text: str) -> Dict[str, Any]:
        """
        Traite le texte d'une offre d'emploi et extrait les informations.
        
        Args:
            text: Texte de l'offre d'emploi
            
        Returns:
            Dictionnaire avec les informations extraites
        """
        if not text:
            return {}
        
        try:
            # Nettoyer le texte
            clean_text = self._clean_text(text.lower())
            
            # Initialiser les résultats
            results = NLPResults()
            results.key_phrases = []
            
            # Traiter avec spaCy si disponible
            if self.nlp:
                doc = self.nlp(clean_text)
                results.key_phrases = self._extract_key_phrases(doc)
            
            # Extraire les informations
            results.experience_years = self._extract_experience_years(clean_text)
            results.sector = self._extract_sector(clean_text)
            results.job_category = self._extract_job_category(clean_text)
            results.job_level = self._extract_job_level(clean_text)
            results.job_type = self._extract_job_type(clean_text)
            results.sentiment_score = self._analyze_sentiment(clean_text)
            results.confidence_score = self._calculate_confidence_score(results)
            
            return {
                'experience_years': results.experience_years,
                'sector': results.sector,
                'job_category': results.job_category,
                'job_level': results.job_level,
                'job_type': results.job_type,
                'sentiment_score': results.sentiment_score,
                'key_phrases': results.key_phrases,
                'confidence_score': results.confidence_score
            }
            
        except Exception as e:
            logging.error(f"Erreur lors du traitement NLP: {e}")
            return {}
    
    def _clean_text(self, text: str) -> str:
        """
        Nettoie le texte en supprimant les caractères spéciaux et normalisant.
        """
        # Supprimer les espaces multiples
        text = re.sub(r'\s+', ' ', text)
        
        # Supprimer les caractères spéciaux tout en gardant l'alphabet français
        text = re.sub(r'[^a-zA-ZÀ-ÿ0-9\s\-\'\"]', ' ', text)
        
        return text.strip()
    
    def _extract_experience_years(self, text: str) -> Optional[int]:
        """
        Extrait les années d'expérience requises.
        """
        for pattern in self.experience_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                try:
                    years = int(matches[0])
                    # Limiter à des valeurs raisonnables
                    if 0 <= years <= 30:
                        return years
                except ValueError:
                    continue
        return None
    
    def _extract_sector(self, text: str) -> Optional[str]:
        """
        Identifie le secteur d'activité principal.
        """
        sector_scores = {}
        
        for sector, keywords in self.sector_keywords.items():
            score = 0
            for keyword in keywords:
                if keyword in text:
                    score += 1
            if score > 0:
                sector_scores[sector] = score
        
        # Retourner le secteur avec le score le plus élevé
        if sector_scores:
            return max(sector_scores, key=sector_scores.get)
        
        return None
    
    def _extract_job_category(self, text: str) -> Optional[str]:
        """
        Extrait la catégorie du poste.
        """
        # Catégories basées sur les mots-clés dans le titre/description
        categories = {
            'Développeur': ['développeur', 'developer', 'programmeur', 'coder'],
            'Chef de projet': ['chef de projet', 'project manager', 'pm'],
            'Ingénieur': ['ingénieur', 'engineer', 'technical lead'],
            'Commercial': ['commercial', 'sales', 'account manager'],
            'Marketing': ['marketing', 'marketeer', 'cmo'],
            'Data Scientist': ['data scientist', 'data analyst', 'data engineer'],
            'Designer': ['designer', 'ui', 'ux', 'graphiste'],
            'Support': ['support', 'helpdesk', 'technicien'],
            'Manager': ['manager', 'directeur', 'responsable']
        }
        
        category_scores = {}
        for category, keywords in categories.items():
            score = sum(1 for keyword in keywords if keyword in text)
            if score > 0:
                category_scores[category] = score
        
        if category_scores:
            return max(category_scores, key=category_scores.get)
        
        return None
    
    def _extract_job_level(self, text: str) -> Optional[str]:
        """
        Détermine le niveau d'expérience du poste.
        """
        level_scores = {}
        
        for level, keywords in self.job_level_keywords.items():
            score = sum(1 for keyword in keywords if keyword in text)
            if score > 0:
                level_scores[level] = score
        
        if level_scores:
            return max(level_scores, key=level_scores.get)
        
        return None
    
    def _extract_job_type(self, text: str) -> Optional[str]:
        """
        Identifie le type de contrat/emploi.
        """
        type_scores = {}
        
        for job_type, keywords in self.job_type_keywords.items():
            score = sum(1 for keyword in keywords if keyword in text)
            if score > 0:
                type_scores[job_type] = score
        
        if type_scores:
            return max(type_scores, key=type_scores.get)
        
        return None
    
    def _analyze_sentiment(self, text: str) -> float:
        """
        Analyse de sentiment basique (fallback léger, pas de dépendance externe).
        Retourne un score entre -1 (très négatif) et +1 (très positif).
        """
        if not text:
            return 0.0

        # Lexique minimal (à étendre)
        positives = {'bon', 'excellente', 'excellent', 'réussite', 'avantage', 'opportunité', 'optimisé', 'proactif', 'solide', 'motivé', 'flexible'}
        negatives = {'mauvais', 'problème', 'difficile', 'urgent', 'stress', 'risque', 'limité', 'fragile', 'faible'}

        score = 0
        words = re.findall(r'\w+', text.lower())
        for w in words:
            if w in positives:
                score += 1
            if w in negatives:
                score -= 1

        # Normaliser entre -1 et 1
        if len(words) == 0:
            return 0.0
        norm = max(min(score / max(len(words) * 0.02, 1.0), 1.0), -1.0)
        return round(norm, 3)
    
    def _extract_key_phrases(self, doc) -> List[str]:
        """
        Extrait les phrases clés du document spaCy.
        """
        key_phrases = []
        
        # Extraire les entités nommées
        for ent in doc.ents:
            if ent.label_ in ['ORG', 'PRODUCT', 'SKILL']:
                key_phrases.append(ent.text)
        
        # Extraire les chunks nominaux importants
        for chunk in doc.noun_chunks:
            if len(chunk.text.split()) <= 4:  # Limiter la longueur
                key_phrases.append(chunk.text)
        
        # Retourner les 10 phrases les plus pertinentes
        return list(set(key_phrases))[:10]
    
    def _calculate_confidence_score(self, results: NLPResults) -> float:
        """
        Calcule un score de confiance basé sur les résultats extraits.
        """
        score = 0.0
        total_possible = 7.0  # Nombre total d'informations possibles
        
        if results.experience_years is not None:
            score += 1.0
        if results.sector is not None:
            score += 1.0
        if results.job_category is not None:
            score += 1.0
        if results.job_level is not None:
            score += 1.0
        if results.job_type is not None:
            score += 1.0
        if results.sentiment_score is not None:
            score += 1.0
        if results.key_phrases and len(results.key_phrases) > 0:
            score += 1.0
        
        return score / total_possible