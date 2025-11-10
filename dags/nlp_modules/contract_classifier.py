"""
Classificateur de contrats pour les offres d'emploi.
Utilise des techniques de classification pour identifier le type de contrat.
"""

import re
import logging
from typing import Optional, List, Dict
from dataclasses import dataclass
from collections import Counter

@dataclass
class ContractInfo:
    """Structure pour stocker les informations de contrat."""
    contract_type: Optional[str] = None
    duration_months: Optional[int] = None
    is_remote: bool = False
    is_full_time: bool = True
    confidence: float = 0.0

class ContractClassifier:
    """
    Classificateur de contrats pour les offres d'emploi.
    """
    
    def __init__(self):
        """
        Initialise le classificateur de contrats.
        """
        # Types de contrats avec leurs mots-clés
        self.contract_types = {
            'CDI': [
                'cdi', 'contrat à durée indéterminée', 'contrat a duree indeterminee',
                'contrat à durée indéterminée', 'permanent contract', 'full-time permanent',
                'emploi permanent', 'poste permanent', 'contrat permanent'
            ],
            'CDD': [
                'cdd', 'contrat à durée déterminée', 'contrat a duree determinee',
                'contrat à durée déterminée', 'fixed-term contract', 'temporary contract',
                'contrat temporaire', 'contrat de remplacement', 'mission temporaire'
            ],
            'Stage': [
                'stage', 'stagiaire', 'internship', 'intern', 'alternance', 'apprentissage',
                'formation en alternance', 'contrat de professionnalisation'
            ],
            'Freelance': [
                'freelance', 'freelancer', 'independent', 'indépendant', 'consultant',
                'consultant externe', 'prestataire', 'sous-traitant', 'contractor'
            ],
            'Intérim': [
                'intérim', 'intérimaire', 'temporaire', 'temporary', 'mission ponctuelle',
                'travail temporaire', 'agence d\'intérim'
            ],
            'Contrat Pro': [
                'contrat pro', 'contrat de professionnalisation', 'alternance',
                'apprentissage', 'formation professionnelle'
            ]
        }
        
        # Patterns pour la durée des contrats
        self.duration_patterns = [
            r'(\d+)\s*(?:mois|month|m)',
            r'(\d+)\s*(?:an|ans|année|années|year|years|a)',
            r'(?:durée|duree|duration)\s*:\s*(\d+)\s*(?:mois|an|ans)',
            r'(?:pour|for)\s*(\d+)\s*(?:mois|an|ans)',
        ]
        
        # Patterns pour le télétravail
        self.remote_patterns = [
            'télétravail', 'teletravail', 'remote', 'work from home', 'home office',
            'à distance', 'a distance', 'remote work', 'fully remote', '100% remote',
            'hybrid', 'télétravail partiel', 'remote partiel'
        ]
        
        # Patterns pour le temps plein/partiel
        self.time_patterns = {
            'full_time': [
                'temps plein', 'full time', 'full-time', '40h', '39h', 'heures plein',
                'full time equivalent', 'fte', 'travail à plein temps'
            ],
            'part_time': [
                'temps partiel', 'part time', 'part-time', 'mi-temps', 'mi temps',
                '20h', '25h', '30h', 'travail à temps partiel'
            ]
        }
        
        # Salaires indicatifs par type de contrat (en XOF mensuel)
        self.salary_indicators = {
            'CDI': (150000, 2000000),  # 150K à 2M FCFA
            'CDD': (120000, 1500000),  # 120K à 1.5M FCFA
            'Stage': (0, 150000),      # 0 à 150K FCFA (stage gratuit possible)
            'Freelance': (200000, 5000000),  # 200K à 5M FCFA
            'Intérim': (100000, 800000),     # 100K à 800K FCFA
            'Contrat Pro': (80000, 300000),  # 80K à 300K FCFA
        }
    
    def classify(self, text: str) -> Optional[str]:
        """
        Classifie le type de contrat dans le texte.
        
        Args:
            text: Texte de l'offre d'emploi
            
        Returns:
            Type de contrat identifié ou None
        """
        if not text:
            return None
        
        try:
            clean_text = text.lower()
            
            # Calculer les scores pour chaque type de contrat
            contract_scores = {}
            
            for contract_type, keywords in self.contract_types.items():
                score = 0
                for keyword in keywords:
                    if keyword.lower() in clean_text:
                        score += 1
                
                if score > 0:
                    contract_scores[contract_type] = score
            
            # Retourner le contrat avec le score le plus élevé
            if contract_scores:
                best_contract = max(contract_scores, key=contract_scores.get)
                
                # Vérifier si le score est suffisamment élevé
                max_score = contract_scores[best_contract]
                if max_score >= 1:  # Au moins une mention
                    return best_contract
            
            # Si aucun contrat clairement identifié, essayer d'inferer à partir du contexte
            return self._infer_contract_type(clean_text)
            
        except Exception as e:
            logging.error(f"Erreur lors de la classification du contrat: {e}")
            return None
    
    def extract_contract_info(self, text: str) -> ContractInfo:
        """
        Extrait toutes les informations de contrat.
        
        Args:
            text: Texte de l'offre d'emploi
            
        Returns:
            Objet ContractInfo avec toutes les informations
        """
        if not text:
            return ContractInfo()
        
        try:
            clean_text = text.lower()
            info = ContractInfo()
            
            # Type de contrat
            info.contract_type = self.classify(text)
            
            # Durée du contrat
            info.duration_months = self._extract_duration(clean_text)
            
            # Télétravail
            info.is_remote = self._detect_remote_work(clean_text)
            
            # Temps plein/partiel
            info.is_full_time = self._detect_full_time(clean_text)
            
            # Score de confiance
            info.confidence = self._calculate_confidence(info, clean_text)
            
            return info
            
        except Exception as e:
            logging.error(f"Erreur lors de l'extraction des infos de contrat: {e}")
            return ContractInfo()
    
    def _infer_contract_type(self, text: str) -> Optional[str]:
        """
        Infère le type de contrat basé sur des indicateurs contextuels.
        """
        # Indicateurs de stage
        stage_indicators = [
            'stagiaire', 'stage', 'apprentissage', 'alternance', 'étudiant',
            'université', 'école', 'formation'
        ]
        
        # Indicateurs de freelance
        freelance_indicators = [
            'prestation', 'mission', 'consultant', 'expert', 'autonome',
            'indépendant', 'facturation', 'taux journalier'
        ]
        
        # Indicateurs d'intérim
        interim_indicators = [
            'intérim', 'remplacement', 'congé', 'maladie', 'mission ponctuelle'
        ]
        
        # Compter les occurrences
        stage_score = sum(1 for indicator in stage_indicators if indicator in text)
        freelance_score = sum(1 for indicator in freelance_indicators if indicator in text)
        interim_score = sum(1 for indicator in interim_indicators if indicator in text)
        
        # Décision basée sur les scores
        if stage_score >= 2:
            return 'Stage'
        elif freelance_score >= 2:
            return 'Freelance'
        elif interim_score >= 2:
            return 'Intérim'
        
        # Par défaut, retourner CDI pour les offres permanentes
        permanent_indicators = ['poste permanent', 'emploi stable', 'carrière']
        if any(indicator in text for indicator in permanent_indicators):
            return 'CDI'
        
        return 'CDI'  # Par défaut
    
    def _extract_duration(self, text: str) -> Optional[int]:
        """Extrait la durée du contrat en mois."""
        for pattern in self.duration_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                try:
                    duration = int(matches[0])
                    
                    # Convertir en mois si nécessaire
                    if 'an' in pattern.lower() or 'year' in pattern.lower():
                        duration *= 12
                    
                    return duration
                except (ValueError, IndexError):
                    continue
        
        return None
    
    def _detect_remote_work(self, text: str) -> bool:
        """Détecte si le poste permet le télétravail."""
        return any(pattern.lower() in text for pattern in self.remote_patterns)
    
    def _detect_full_time(self, text: str) -> bool:
        """Détecte si le poste est à temps plein."""
        full_time_score = sum(1 for pattern in self.time_patterns['full_time'] if pattern.lower() in text)
        part_time_score = sum(1 for pattern in self.time_patterns['part_time'] if pattern.lower() in text)
        
        return full_time_score >= part_time_score
    
    def _calculate_confidence(self, info: ContractInfo, text: str) -> float:
        """Calcule un score de confiance pour l'extraction."""
        confidence = 0.0
        
        # Bonus pour avoir identifié un type de contrat
        if info.contract_type:
            confidence += 0.4
        
        # Bonus pour avoir trouvé la durée
        if info.duration_months:
            confidence += 0.2
        
        # Bonus pour le télétravail
        if info.is_remote:
            confidence += 0.2
        
        # Bonus pour avoir identifié le temps de travail
        confidence += 0.2
        
        return min(confidence, 1.0)
    
    def get_contract_recommendations(self, salary_min: Optional[int], salary_max: Optional[int]) -> List[str]:
        """
        Recommande des types de contrat basés sur la fourchette salariale.
        
        Args:
            salary_min: Salaire minimum
            salary_max: Salaire maximum
            
        Returns:
            Liste de types de contrat recommandés
        """
        recommendations = []
        
        if not salary_min and not salary_max:
            return recommendations
        
        # Utiliser le salaire moyen pour l'analyse
        avg_salary = (salary_min or 0 + salary_max or 0) / 2 if salary_min or salary_max else 0
        
        for contract_type, (min_range, max_range) in self.salary_indicators.items():
            if min_range <= avg_salary <= max_range:
                recommendations.append(contract_type)
        
        return recommendations[:3]  # Limiter à 3 recommandations
    
    def validate_contract_salary(self, contract_type: str, salary_min: Optional[int], salary_max: Optional[int]) -> bool:
        """
        Valide si un salaire est cohérent avec un type de contrat.
        
        Args:
            contract_type: Type de contrat
            salary_min: Salaire minimum
            salary_max: Salaire maximum
            
        Returns:
            True si le salaire est cohérent avec le contrat
        """
        if not contract_type or (not salary_min and not salary_max):
            return True  # Pas assez d'informations pour invalider
        
        avg_salary = (salary_min or 0 + salary_max or 0) / 2 if salary_min or salary_max else 0
        
        if contract_type in self.salary_indicators:
            min_range, max_range = self.salary_indicators[contract_type]
            return min_range <= avg_salary <= max_range
        
        return True  # Pas de données de référence, on valide