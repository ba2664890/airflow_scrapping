"""
Extracteur de compétences à partir de textes d'offres d'emploi.
Utilise des techniques de NLP et des référentiels de compétences.
"""

import re
import logging
from typing import List, Set, Dict, Optional
import json
import os

class SkillExtractor:
    """
    Classe pour extraire les compétences techniques et soft skills des offres d'emploi.
    """
    
    def __init__(self):
        """
        Initialise l'extracteur de compétences avec des référentiels de compétences.
        """
        # Compétences techniques par catégorie
        self.technical_skills = {
            'Programming Languages': [
                'python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'php', 'ruby', 'go', 'rust',
                'swift', 'kotlin', 'scala', 'r', 'matlab', 'sql', 'html', 'css', 'sass', 'less'
            ],
            'Frameworks & Libraries': [
                'react', 'angular', 'vue', 'next.js', 'nuxt.js', 'django', 'flask', 'spring', 'laravel',
                'rails', 'express', 'node.js', 'jquery', 'bootstrap', 'tailwind', 'material-ui',
                'redux', 'mobx', 'graphql', 'rest api', 'fastapi', 'pandas', 'numpy', 'scikit-learn'
            ],
            'Databases': [
                'mysql', 'postgresql', 'mongodb', 'redis', 'elasticsearch', 'cassandra', 'oracle',
                'sql server', 'sqlite', 'firebase', 'dynamodb', 'neo4j', 'influxdb'
            ],
            'Cloud & DevOps': [
                'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'jenkins', 'gitlab ci', 'github actions',
                'terraform', 'ansible', 'chef', 'puppet', 'prometheus', 'grafana', 'elk stack',
                'microservices', 'ci/cd', 'devops', 'agile', 'scrum'
            ],
            'Data Science & ML': [
                'machine learning', 'deep learning', 'neural networks', 'tensorflow', 'pytorch',
                'keras', 'opencv', 'nlp', 'computer vision', 'data mining', 'statistical analysis',
                'a/b testing', 'feature engineering', 'model deployment', 'mlflow', 'airflow'
            ],
            'Mobile Development': [
                'android', 'ios', 'react native', 'flutter', 'ionic', 'cordova', 'phonegap',
                'swift', 'objective-c', 'java mobile', 'kotlin android', 'xamarin'
            ],
            'Design & UX': [
                'figma', 'adobe xd', 'sketch', 'photoshop', 'illustrator', 'invision', 'zeplin',
                'user research', 'wireframing', 'prototyping', 'user testing', 'design system',
                'responsive design', 'mobile first', 'accessibility'
            ],
            'Business & Management': [
                'project management', 'product management', 'business analysis', 'strategic planning',
                'team leadership', 'budget management', 'risk management', 'change management',
                'stakeholder management', 'vendor management', 'quality assurance'
            ]
        }
        
        # Soft skills
        self.soft_skills = [
            'communication', 'leadership', 'teamwork', 'collaboration', 'problem solving',
            'critical thinking', 'creativity', 'adaptability', 'time management',
            'organizational skills', 'analytical skills', 'interpersonal skills',
            'presentation skills', 'negotiation', 'conflict resolution', 'empathy',
            'emotional intelligence', 'stress management', 'decision making',
            'strategic thinking', 'innovation', 'customer service', 'relationship building'
        ]
        
        # Créer des ensembles pour une recherche rapide
        self.all_technical_skills = set()
        for category_skills in self.technical_skills.values():
            self.all_technical_skills.update(category_skills)
        
        self.all_soft_skills = set(self.soft_skills)
        
        # Patterns regex pour les compétences complexes
        self.skill_patterns = {
            'cloud_certifications': r'\b(AWS|Azure|GCP)\s+(Certified|Professional|Associate|Solutions Architect)\b',
            'microsoft_tools': r'\b(MS\s+Office|Microsoft\s+(Word|Excel|PowerPoint|Outlook|Teams))\b',
            'project_methodologies': r'\b(Agile|Scrum|Kanban|Waterfall|Lean|Six\s+Sigma)\b',
            'languages': r'\b(Français|Anglais|Arabe|Espagnol|Allemand|Portugais)\s+(courant|bilingue|natif|avancé|intermédiaire)\b',
            'certifications': r'\b(PMP|MBA|PHR|SPHR|ITIL|Six\s+Sigma|ISO\s+\d+)\b'
        }
    
    def extract_skills(self, text: str) -> List[str]:
        """
        Extrait toutes les compétences du texte.
        
        Args:
            text: Texte de l'offre d'emploi
            
        Returns:
            Liste de compétences uniques trouvées
        """
        if not text:
            return []
        
        try:
            # Nettoyer le texte
            clean_text = text.lower()
            
            # Ensemble pour stocker les compétences trouvées
            found_skills = set()
            
            # Extraire les compétences techniques
            found_skills.update(self._extract_technical_skills(clean_text))
            
            # Extraire les soft skills
            found_skills.update(self._extract_soft_skills(clean_text))
            
            # Extraire les compétences avec patterns regex
            found_skills.update(self._extract_pattern_skills(clean_text))
            
            # Extraire les compétences contextuelles
            found_skills.update(self._extract_contextual_skills(clean_text))
            
            # Filtrer et normaliser les résultats
            final_skills = self._normalize_skills(found_skills)
            
            # Retourner les compétences triées par pertinence
            return sorted(final_skills)[:20]  # Limiter à 20 compétences max
            
        except Exception as e:
            logging.error(f"Erreur lors de l'extraction des compétences: {e}")
            return []
    
    def _extract_technical_skills(self, text: str) -> Set[str]:
        """Extrait les compétences techniques."""
        found_skills = set()
        
        for skill in self.all_technical_skills:
            if skill.lower() in text:
                found_skills.add(skill.title())
        
        return found_skills
    
    def _extract_soft_skills(self, text: str) -> Set[str]:
        """Extrait les soft skills."""
        found_skills = set()
        
        for skill in self.all_soft_skills:
            if skill.lower() in text:
                found_skills.add(skill.title())
        
        return found_skills
    
    def _extract_pattern_skills(self, text: str) -> Set[str]:
        """Extrait les compétences avec patterns regex."""
        found_skills = set()
        
        for pattern_name, pattern in self.skill_patterns.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    found_skills.add(' '.join(match).title())
                else:
                    found_skills.add(match.title())
        
        return found_skills
    
    def _extract_contextual_skills(self, text: str) -> Set[str]:
        """Extrait les compétences basées sur le contexte."""
        found_skills = set()
        
        # Patterns contextuels
        contextual_patterns = {
            'Gestion de projet': ['gestion de projet', 'project management', 'management de projet'],
            'Analyse de données': ['analyse de données', 'data analysis', 'analyse des données'],
            'Développement web': ['développement web', 'web development', 'développement frontend', 'développement backend'],
            'Business Intelligence': ['business intelligence', 'bi', 'intelligence d\'affaires'],
            'Sécurité informatique': ['cybersécurité', 'sécurité informatique', 'security', 'pentest'],
            'Cloud computing': ['cloud computing', 'cloud', 'infrastructure cloud'],
            'Machine Learning': ['machine learning', 'apprentissage automatique', 'ml'],
            'Big Data': ['big data', 'données massives', 'data engineering'],
            'DevOps': ['devops', 'devops culture', 'infrastructure as code'],
            'Mobile Development': ['développement mobile', 'mobile development', 'mobile app']
        }
        
        for skill_name, patterns in contextual_patterns.items():
            for pattern in patterns:
                if pattern.lower() in text:
                    found_skills.add(skill_name)
                    break
        
        return found_skills
    
    def _normalize_skills(self, skills: Set[str]) -> List[str]:
        """Normalise et filtre les compétences trouvées."""
        normalized = []
        
        for skill in skills:
            # Nettoyer la compétence
            clean_skill = skill.strip()
            
            # Ignorer les compétences trop courtes ou trop longues
            if len(clean_skill) < 3 or len(clean_skill) > 50:
                continue
            
            # Ignorer les compétences trop génériques
            generic_terms = ['skill', 'competence', 'ability', 'capacité', 'capacite']
            if any(term in clean_skill.lower() for term in generic_terms):
                continue
            
            normalized.append(clean_skill)
        
        # Retirer les doublons et trier
        return sorted(set(normalized))
    
    def get_skill_categories(self, skills: List[str]) -> Dict[str, List[str]]:
        """
        Catégorise les compétences par type.
        
        Args:
            skills: Liste des compétences
            
        Returns:
            Dictionnaire avec les compétences catégorisées
        """
        categorized = {
            'technical': [],
            'soft_skills': [],
            'languages': [],
            'certifications': [],
            'other': []
        }
        
        for skill in skills:
            skill_lower = skill.lower()
            
            # Vérifier si c'est une compétence technique
            is_technical = False
            for category_skills in self.technical_skills.values():
                if any(tech_skill.lower() in skill_lower for tech_skill in category_skills):
                    categorized['technical'].append(skill)
                    is_technical = True
                    break
            
            # Vérifier si c'est une soft skill
            if not is_technical and any(soft_skill.lower() in skill_lower for soft_skill in self.soft_skills):
                categorized['soft_skills'].append(skill)
            
            # Vérifier si c'est une langue
            elif not is_technical and any(lang.lower() in skill_lower for lang in ['français', 'anglais', 'arabe', 'espagnol', 'allemand']):
                categorized['languages'].append(skill)
            
            # Vérifier si c'est une certification
            elif not is_technical and any(cert.lower() in skill_lower for cert in ['certified', 'certification', 'pmp', 'mba', 'itil']):
                categorized['certifications'].append(skill)
            
            # Sinon, mettre dans 'other'
            elif not is_technical:
                categorized['other'].append(skill)
        
        return categorized
    
    def save_skill_referential(self, filepath: str):
        """
        Sauvegarde le référentiel des compétences.
        
        Args:
            filepath: Chemin du fichier de sauvegarde
        """
        referential = {
            'technical_skills': self.technical_skills,
            'soft_skills': self.soft_skills,
            'skill_patterns': self.skill_patterns,
            'last_updated': pd.Timestamp.now().isoformat()
        }
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(referential, f, indent=2, ensure_ascii=False)
            logging.info(f"Référentiel des compétences sauvegardé: {filepath}")
        except Exception as e:
            logging.error(f"Erreur lors de la sauvegarde du référentiel: {e}")
    
    def load_skill_referential(self, filepath: str):
        """
        Charge un référentiel des compétences.
        
        Args:
            filepath: Chemin du fichier à charger
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                referential = json.load(f)
            
            self.technical_skills = referential.get('technical_skills', self.technical_skills)
            self.soft_skills = referential.get('soft_skills', self.soft_skills)
            self.skill_patterns = referential.get('skill_patterns', self.skill_patterns)
            
            # Recréer les ensembles
            self.all_technical_skills = set()
            for category_skills in self.technical_skills.values():
                self.all_technical_skills.update(category_skills)
            
            self.all_soft_skills = set(self.soft_skills)
            
            logging.info(f"Référentiel des compétences chargé: {filepath}")
            
        except Exception as e:
            logging.error(f"Erreur lors du chargement du référentiel: {e}")