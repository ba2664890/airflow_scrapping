"""
Extracteur de salaires à partir de textes d'offres d'emploi.
Utilise des techniques de NLP et des patterns regex pour identifier les fourchettes salariales.
"""

import re
import logging
from typing import Dict, Optional, Any
from dataclasses import dataclass
import pandas as pd

@dataclass
class SalaryInfo:
    """Structure pour stocker les informations de salaire."""
    min_salary: Optional[int] = None
    max_salary: Optional[int] = None
    currency: Optional[str] = None
    period: Optional[str] = None  # 'monthly', 'yearly', 'hourly'
    original_text: Optional[str] = None
    confidence: Optional[float] = None

class SalaryExtractor:
    """
    Extracteur de salaires pour les offres d'emploi au Sénégal.
    """
    
    def __init__(self):
        """
        Initialise l'extracteur de salaires.
        """
        # Patterns pour les différentes devises
        self.currency_patterns = {
            'XOF': [
                r'[\d\s]+\s*(FCFA|CFA|XOF|Francs? CFA|F CFA)',
                r'[\d\s]+\s*(francs?|f|F)\s*(CFA|cfa)',
                r'CFA\s*[\d\s,]+',
                r'XOF\s*[\d\s,]+'
            ],
            'EUR': [
                r'[\d\s]+\s*(€|EUR|euros?)',
                r'€\s*[\d\s,]+',
                r'EUR\s*[\d\s,]+'
            ],
            'USD': [
                r'[\d\s]+\s*(\$|USD|dollars?)',
                r'\$\s*[\d\s,]+',
                r'USD\s*[\d\s,]+'
            ],
            'GBP': [
                r'[\d\s]+\s*(£|GBP|livres?)',
                r'£\s*[\d\s,]+',
                r'GBP\s*[\d\s,]+'
            ]
        }
        
        # Patterns pour les fourchettes salariales
        self.salary_range_patterns = [
            # Format: X à Y
            r'(\d+(?:\s*\d*)*)\s*(?:à|a|to|-)\s*(\d+(?:\s*\d*)*)\s*(?:FCFA|CFA|€|\$|XOF|EUR|USD)',
            # Format: X-Y
            r'(\d+(?:\s*\d*)*)\s*-\s*(\d+(?:\s*\d*)*)\s*(?:FCFA|CFA|€|\$|XOF|EUR|USD)',
            # Format: entre X et Y
            r'entre\s+(\d+(?:\s*\d*)*)\s*(?:et|and)\s+(\d+(?:\s*\d*)*)\s*(?:FCFA|CFA|€|\$|XOF|EUR|USD)',
            # Format: de X à Y
            r'de\s+(\d+(?:\s*\d*)*)\s*(?:à|a|to)\s+(\d+(?:\s*\d*)*)\s*(?:FCFA|CFA|€|\$|XOF|EUR|USD)',
        ]
        
        # Patterns pour les salaires uniques
        self.single_salary_patterns = [
            r'(\d+(?:\s*\d*)*)\s*(?:FCFA|CFA|€|\$|XOF|EUR|USD)',
            r'(?:salaire|salaire de|rémunération|rémunéré à|rémunéré de)\s+(\d+(?:\s*\d*)*)',
        ]
        
        # Patterns pour les périodes
        self.period_patterns = {
            'monthly': [
                r'(?:par|/|par\s+)mois',
                r'mensuel|mensuelle',
                r'monthly',
                r'/mois|par mois'
            ],
            'yearly': [
                r'(?:par|/|par\s+)an(?:née)?|(?:par|/|par\s+)ans',
                r'annuel|annuelle',
                r'yearly|annual',
                r'/an|par an'
            ],
            'hourly': [
                r'(?:par|/|par\s+)heure',
                r'horaire',
                r'hourly',
                r'/h|/heure|par heure'
            ],
            'daily': [
                r'(?:par|/|par\s+)jour(?:née)?',
                r'journalier|quotidien',
                r'daily',
                r'/jour|par jour'
            ]
        }
        
        # Salaires minimums et maximums raisonnables par devise et période
        self.reasonable_ranges = {
            'XOF': {
                'monthly': (50000, 5000000),  # 50K à 5M FCFA par mois
                'yearly': (600000, 60000000),  # 600K à 60M FCFA par an
                'hourly': (500, 50000),  # 500 à 50K FCFA par heure
                'daily': (2000, 200000)  # 2K à 200K FCFA par jour
            },
            'EUR': {
                'monthly': (500, 50000),  # 500 à 50K EUR par mois
                'yearly': (6000, 600000),  # 6K à 600K EUR par an
                'hourly': (5, 500),  # 5 à 500 EUR par heure
                'daily': (40, 4000)  # 40 à 4K EUR par jour
            },
            'USD': {
                'monthly': (600, 60000),  # 600 à 60K USD par mois
                'yearly': (7200, 720000),  # 7.2K à 720K USD par an
                'hourly': (6, 600),  # 6 à 600 USD par heure
                'daily': (50, 5000)  # 50 à 5K USD par jour
            }
        }
        
        # Salaires de référence pour le Sénégal (en XOF)
        self.senegal_benchmarks = {
            'minimum_wage': 58000,  # SMIG mensuel
            'average_salary': 200000,  # Salaire moyen mensuel
            'executive_salary': 1000000,  # Salaire cadre mensuel
            'minimum_wage_annual': 696000,  # SMIG annuel
        }
    
    def extract_salary(self, text: str) -> Dict[str, Any]:
        """
        Extrait les informations de salaire du texte.
        """
        if not text:
            return {
                'min_salary': None,
                'max_salary': None,
                'currency': None,
                'period': None,
                'confidence': 0.0,
                'original_text': ''
            }
        
        try:
            clean_text = text.lower()
            
            # D'abord, essayer d'extraire une fourchette salariale
            salary_info = self._extract_salary_range(clean_text)
            # Si pas de fourchette, essayer un salaire unique
            if salary_info.min_salary is None and salary_info.max_salary is None:
                salary_info = self._extract_single_salary(clean_text)
            
            # Extraire la devise et la période
            salary_info.currency = self._extract_currency(clean_text)
            salary_info.period = self._extract_period(clean_text)
            
            # Normaliser les salaires
            self._normalize_salaries(salary_info)
            
            # Calculer le score de confiance
            salary_info.confidence = self._calculate_confidence(salary_info)
            
            return {
                'min_salary': salary_info.min_salary,
                'max_salary': salary_info.max_salary,
                'currency': salary_info.currency,
                'period': salary_info.period,
                'confidence': salary_info.confidence,
                'original_text': text[:200] + '...' if len(text) > 200 else text
            }
            
        except Exception as e:
            logging.error(f"Erreur lors de l'extraction du salaire: {e}")
            return {
                'min_salary': None,
                'max_salary': None,
                'currency': None,
                'period': None,
                'confidence': 0.0,
                'original_text': text[:200] + '...' if text else ''
            }
    
    def _extract_salary_range(self, text: str) -> SalaryInfo:
        """Extrait une fourchette salariale."""
        info = SalaryInfo()
        
        for pattern in self.salary_range_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                try:
                    min_sal = self._parse_salary_number(matches[0][0])
                    max_sal = self._parse_salary_number(matches[0][1])
                    
                    if min_sal and max_sal and min_sal <= max_sal:
                        info.min_salary = min_sal
                        info.max_salary = max_sal
                        break
                        
                except (ValueError, IndexError):
                    continue
        
        return info
    
    def _extract_single_salary(self, text: str) -> SalaryInfo:
        """Extrait un salaire unique."""
        info = SalaryInfo()
        
        for pattern in self.single_salary_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                try:
                    salary = self._parse_salary_number(matches[0])
                    if salary:
                        info.min_salary = salary
                        info.max_salary = salary
                        break
                        
                except (ValueError, IndexError):
                    continue
        
        return info
    
    def _extract_currency(self, text: str) -> Optional[str]:
        """Extrait la devise."""
        for currency, patterns in self.currency_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return currency
        
        # Par défaut, retourner XOF pour les offres sénégalaises
        if any(indicator in text for indicator in ['senegal', 'dakar', 'sénégal']):
            return 'XOF'
        
        return 'XOF'  # Devise par défaut
    
    def _extract_period(self, text: str) -> Optional[str]:
        """Extrait la période de paiement."""
        for period, patterns in self.period_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return period
        
        # Par défaut, mensuel pour les salaires sénégalais
        return 'monthly'
    
    def _parse_salary_number(self, salary_str: str) -> Optional[int]:
        """Parse un nombre de salaire."""
        try:
            # Nettoyer la chaîne
            if isinstance(salary_str, (list, tuple)):
                salary_str = salary_str[0]
            clean_str = re.sub(r'[^\d]', '', str(salary_str))
            
            if not clean_str:
                return None
            
            salary = int(clean_str)
            
            # Ajuster les salaires qui semblent être annuels mais sans zéros
            if 1000 <= salary <= 99999:
                # Probablement un salaire mensuel
                return salary
            elif 100 <= salary <= 999:
                # Peut-être un salaire en milliers
                return salary * 1000
            elif salary < 100:
            # Probablement un salaire horaire/journalier
                return salary * 1000  # Convertir en mensuel approximatif
            
            return salary
            
        except ValueError:
            return None
    
    def _normalize_salaries(self, salary_info: SalaryInfo):
        """Normalise les salaires selon la période et la devise."""
        if not salary_info.min_salary:
            return
        
        # Convertir en salaire mensuel si nécessaire
        if salary_info.period == 'yearly':
            salary_info.min_salary = int(salary_info.min_salary / 12)
            if salary_info.max_salary:
                salary_info.max_salary = int(salary_info.max_salary / 12)
        
        elif salary_info.period == 'hourly':
            # Convertir en mensuel (160 heures par mois en moyenne)
            salary_info.min_salary = int(salary_info.min_salary * 160)
            if salary_info.max_salary:
                salary_info.max_salary = int(salary_info.max_salary * 160)
        
        elif salary_info.period == 'daily':
            # Convertir en mensuel (22 jours ouvrables par mois)
            salary_info.min_salary = int(salary_info.min_salary * 22)
            if salary_info.max_salary:
                salary_info.max_salary = int(salary_info.max_salary * 22)
        
        # Convertir en XOF si nécessaire (taux approximatifs)
        if salary_info.currency == 'EUR':
            conversion_rate = 655.957  # Taux fixe CFA/EUR
            salary_info.min_salary = int(salary_info.min_salary * conversion_rate)
            if salary_info.max_salary:
                salary_info.max_salary = int(salary_info.max_salary * conversion_rate)
        
        elif salary_info.currency == 'USD':
            conversion_rate = 600  # Taux approximatif CFA/USD
            salary_info.min_salary = int(salary_info.min_salary * conversion_rate)
            if salary_info.max_salary:
                salary_info.max_salary = int(salary_info.max_salary * conversion_rate)
        
        elif salary_info.currency == 'GBP':
            conversion_rate = 750  # Taux approximatif CFA/GBP
            salary_info.min_salary = int(salary_info.min_salary * conversion_rate)
            if salary_info.max_salary:
                salary_info.max_salary = int(salary_info.max_salary * conversion_rate)
        
        # S'assurer que la devise est XOF à la fin
        salary_info.currency = 'XOF'
        salary_info.period = 'monthly'
    
    def _calculate_confidence(self, salary_info: SalaryInfo) -> float:
        """Calcule un score de confiance pour l'extraction."""
        confidence = 0.0
        
        # Bonus pour avoir trouvé un salaire
        if salary_info.min_salary:
            confidence += 0.3
        
        # Bonus pour avoir une fourchette complète
        if salary_info.min_salary and salary_info.max_salary:
            confidence += 0.3
        
        # Bonus pour avoir identifié la devise
        if salary_info.currency:
            confidence += 0.2
        
        # Bonus pour avoir identifié la période
        if salary_info.period:
            confidence += 0.2
        
        # Vérifier si le salaire est dans une plage raisonnable
        if salary_info.min_salary:
            reasonable_range = self.reasonable_ranges.get(salary_info.currency, {}).get(salary_info.period, (0, float('inf')))
            if reasonable_range[0] <= salary_info.min_salary <= reasonable_range[1]:
                confidence += 0.1
            else:
                confidence -= 0.2  # Pénaliser les salaires irréalistes
        
        return min(confidence, 1.0)  # Limiter à 1.0 maximum