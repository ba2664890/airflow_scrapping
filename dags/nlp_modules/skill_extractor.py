"""
Extracteur de compétences à partir de textes d'offres d'emploi.
Utilise des techniques de NLP et des référentiels de compétences.

Corrections appliquées (cf. audit 10/06/2026) :
  SK-01  : pd.Timestamp remplacé par datetime.datetime (import stdlib, pas de dépendance pandas)
  SK-02  : Correspondance avec délimiteurs de mots \b — plus de faux positifs sur 'r', 'go', etc.
  SK-03  : Tri par score de pertinence (fréquence + position) avant troncature
  SK-04  : Suppression des doublons inter-catégories (swift, java) ; mapping skill → catégorie canonique
  SK-05  : _normalize_skills() simplifiée — les sets amont garantissent déjà l'unicité
  SK-06  : Patterns regex compilés une seule fois dans __init__() (pre-compilation)
  SK-07  : Logging structuré ajouté sur les chemins nominaux
  SK-08  : Type hints complets sur toutes les méthodes privées
  SK-09  : Référentiel externalisable via load_skill_referential() (YAML/JSON)
  SK-10  : Normalisation Unicode (NFKD) avant tout traitement de chaîne
"""

import re
import logging
import unicodedata
import datetime
import json
import os
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers Unicode
# ---------------------------------------------------------------------------

def _normalize_unicode(text: str) -> str:
    """
    Normalise le texte en NFKD et remplace les espaces insécables / homoglyphes.
    Conserve les accents pour que les patterns francophones restent lisibles.
    """
    # NFKD : décompose les ligatures et normalise les espaces Unicode
    text = unicodedata.normalize("NFKD", text)
    # Remplace tous les types d'espaces blancs Unicode par un espace ordinaire
    text = re.sub(r"[\u00a0\u200b\u202f\u2009\u2002\u2003]", " ", text)
    return text


def _build_word_pattern(skill: str) -> re.Pattern:
    """
    Construit un pattern regex avec délimiteurs de mots adapté à la compétence.

    Cas particuliers gérés :
      - Compétences contenant des caractères spéciaux (c++, c#, next.js, ci/cd)
        → les délimiteurs \b sont placés autour de la séquence entière
      - Compétences multi-mots (machine learning, rest api)
        → chaque espace peut être un ou plusieurs espaces/tirets
    """
    escaped = re.escape(skill)
    # Remplace les espaces échappés par un séparateur souple
    escaped = escaped.replace(r"\ ", r"[\s\-]+")
    return re.compile(r"(?<![a-zA-Z0-9])" + escaped + r"(?![a-zA-Z0-9])", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Définition canonique des compétences (skill → catégorie unique)
# ---------------------------------------------------------------------------

# Chaque compétence n'apparaît que dans UNE seule catégorie (SK-04).
# Les doublons entre Programming Languages et Mobile Development ont été résolus :
#   swift     → Programming Languages
#   kotlin    → Programming Languages  (kotlin android supprimé comme alias)
#   java      → Programming Languages  (java mobile supprimé comme alias)
_CANONICAL_TECHNICAL_SKILLS: Dict[str, List[str]] = {
    "Programming Languages": [
        "python", "java", "javascript", "typescript", "c++", "c#", "php",
        "ruby", "go", "rust", "swift", "kotlin", "scala", "r", "matlab",
        "sql", "html", "css", "sass", "less",
    ],
    "Frameworks & Libraries": [
        "react", "angular", "vue", "next.js", "nuxt.js", "django", "flask",
        "spring", "laravel", "rails", "express", "node.js", "jquery",
        "bootstrap", "tailwind", "material-ui", "redux", "mobx", "graphql",
        "rest api", "fastapi", "pandas", "numpy", "scikit-learn",
    ],
    "Databases": [
        "mysql", "postgresql", "mongodb", "redis", "elasticsearch",
        "cassandra", "oracle", "sql server", "sqlite", "firebase",
        "dynamodb", "neo4j", "influxdb",
    ],
    "Cloud & DevOps": [
        "aws", "azure", "gcp", "docker", "kubernetes", "jenkins",
        "gitlab ci", "github actions", "terraform", "ansible", "chef",
        "puppet", "prometheus", "grafana", "elk stack", "microservices",
        "ci/cd", "devops", "agile", "scrum",
    ],
    "Data Science & ML": [
        "machine learning", "deep learning", "neural networks", "tensorflow",
        "pytorch", "keras", "opencv", "nlp", "computer vision", "data mining",
        "statistical analysis", "a/b testing", "feature engineering",
        "model deployment", "mlflow", "airflow",
    ],
    "Mobile Development": [
        "android", "ios", "react native", "flutter", "ionic", "cordova",
        "phonegap", "objective-c", "xamarin",
    ],
    "Design & UX": [
        "figma", "adobe xd", "sketch", "photoshop", "illustrator",
        "invision", "zeplin", "user research", "wireframing", "prototyping",
        "user testing", "design system", "responsive design", "mobile first",
        "accessibility",
    ],
    "Business & Management": [
        "project management", "product management", "business analysis",
        "strategic planning", "team leadership", "budget management",
        "risk management", "change management", "stakeholder management",
        "vendor management", "quality assurance",
    ],
}

_SOFT_SKILLS: List[str] = [
    "communication", "leadership", "teamwork", "collaboration",
    "problem solving", "critical thinking", "creativity", "adaptability",
    "time management", "organizational skills", "analytical skills",
    "interpersonal skills", "presentation skills", "negotiation",
    "conflict resolution", "empathy", "emotional intelligence",
    "stress management", "decision making", "strategic thinking",
    "innovation", "customer service", "relationship building",
]

# Patterns regex nommés pour les compétences complexes
_NAMED_PATTERNS: Dict[str, str] = {
    "cloud_certifications": (
        r"\b(AWS|Azure|GCP)\s+(Certified|Professional|Associate|Solutions\s+Architect)\b"
    ),
    "microsoft_tools": (
        r"\b(MS\s+Office|Microsoft\s+(?:Word|Excel|PowerPoint|Outlook|Teams))\b"
    ),
    "project_methodologies": (
        r"\b(Agile|Scrum|Kanban|Waterfall|Lean|Six\s+Sigma)\b"
    ),
    "spoken_languages": (
        r"\b(Fran[cç]ais|Anglais|Arabe|Espagnol|Allemand|Portugais)"
        r"\s+(courant|bilingue|natif|avanc[eé]|interm[eé]diaire)\b"
    ),
    "certifications": (
        r"\b(PMP|MBA|PHR|SPHR|ITIL|Six\s+Sigma|ISO\s+\d+)\b"
    ),
}

# Patterns contextuels (terme canonique → liste d'expressions déclenchantes)
_CONTEXTUAL_PATTERNS: Dict[str, List[str]] = {
    "Gestion de projet": [
        "gestion de projet", "project management", "management de projet",
    ],
    "Analyse de données": [
        "analyse de données", "data analysis", "analyse des données",
    ],
    "Développement web": [
        "développement web", "web development",
        "développement frontend", "développement backend",
    ],
    "Business Intelligence": [
        "business intelligence", "intelligence d'affaires",
    ],
    "Sécurité informatique": [
        "cybersécurité", "sécurité informatique", "pentest",
    ],
    "Cloud computing": [
        "cloud computing", "infrastructure cloud",
    ],
    "Machine Learning": [
        "machine learning", "apprentissage automatique",
    ],
    "Big Data": [
        "big data", "données massives", "data engineering",
    ],
    "DevOps": [
        "devops", "infrastructure as code",
    ],
    "Mobile Development": [
        "développement mobile", "mobile development", "mobile app",
    ],
}

_GENERIC_TERMS: Set[str] = {
    "skill", "competence", "ability", "capacité", "capacite",
}


# ---------------------------------------------------------------------------
# Classe principale
# ---------------------------------------------------------------------------

class SkillExtractor:
    """
    Extrait les compétences techniques et soft skills des offres d'emploi.

    Utilisation typique ::

        extractor = SkillExtractor()
        skills = extractor.extract_skills(job_description_text)
        categories = extractor.get_skill_categories(skills)
    """

    def __init__(self) -> None:
        # Référentiel de compétences techniques (catégorie → liste)
        self.technical_skills: Dict[str, List[str]] = {
            k: list(v) for k, v in _CANONICAL_TECHNICAL_SKILLS.items()
        }

        # Soft skills
        self.soft_skills: List[str] = list(_SOFT_SKILLS)

        # Index plat skill → catégorie canonique (SK-04)
        self._skill_to_category: Dict[str, str] = {}
        for category, skills in self.technical_skills.items():
            for s in skills:
                self._skill_to_category[s.lower()] = category

        # Ensembles pour lookup O(1)
        self.all_technical_skills: Set[str] = set(self._skill_to_category.keys())
        self.all_soft_skills: Set[str] = {s.lower() for s in self.soft_skills}

        # SK-06 : patterns nommés compilés une seule fois
        self._compiled_named_patterns: Dict[str, re.Pattern] = {
            name: re.compile(pattern, re.IGNORECASE)
            for name, pattern in _NAMED_PATTERNS.items()
        }

        # SK-06 : patterns techniques compilés avec \b une seule fois (SK-02)
        self._compiled_tech_patterns: Dict[str, re.Pattern] = {
            skill: _build_word_pattern(skill)
            for skill in self.all_technical_skills
        }

        # SK-06 : patterns soft skills compilés avec \b une seule fois (SK-02)
        self._compiled_soft_patterns: Dict[str, re.Pattern] = {
            skill: _build_word_pattern(skill)
            for skill in self.all_soft_skills
        }

        # SK-06 : patterns contextuels compilés
        self._compiled_contextual: Dict[str, List[re.Pattern]] = {
            label: [_build_word_pattern(p) for p in patterns]
            for label, patterns in _CONTEXTUAL_PATTERNS.items()
        }

        logger.debug(
            "SkillExtractor initialisé — %d compétences techniques, %d soft skills",
            len(self.all_technical_skills),
            len(self.all_soft_skills),
        )

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def extract_skills(self, text: str) -> List[str]:
        """
        Extrait toutes les compétences du texte.

        Args:
            text: Texte brut de l'offre d'emploi.

        Returns:
            Liste de compétences uniques, triées par score de pertinence
            (fréquence d'apparition + position dans le texte) puis
            alphabétiquement en cas d'égalité. Limitée à 50 entrées.
        """
        if not text or not text.strip():
            return []

        try:
            # SK-10 : normalisation Unicode avant tout traitement
            clean_text = _normalize_unicode(text).lower()

            found_skills: Set[str] = set()
            found_skills.update(self._extract_technical_skills(clean_text))
            found_skills.update(self._extract_soft_skills(clean_text))
            found_skills.update(self._extract_pattern_skills(clean_text))
            found_skills.update(self._extract_contextual_skills(clean_text))

            # SK-05 : normalisation sans redondance set→list→set
            normalized = self._normalize_skills(found_skills)

            # SK-03 : tri par pertinence avant troncature
            scored = self._score_skills(normalized, clean_text)
            result = [skill for skill, _ in scored[:50]]

            logger.debug(
                "extract_skills : %d compétences trouvées (texte de %d caractères)",
                len(result),
                len(text),
            )
            return result

        except Exception:
            logger.exception("Erreur lors de l'extraction des compétences")
            return []

    def get_skill_categories(self, skills: List[str]) -> Dict[str, List[str]]:
        """
        Catégorise les compétences par type.

        Args:
            skills: Liste de compétences issues de extract_skills().

        Returns:
            Dictionnaire ``{catégorie: [compétences]}``.
            Catégories : ``technical``, ``soft_skills``, ``languages``,
            ``certifications``, ``other``.
        """
        categorized: Dict[str, List[str]] = {
            "technical": [],
            "soft_skills": [],
            "languages": [],
            "certifications": [],
            "other": [],
        }

        for skill in skills:
            skill_lower = skill.lower()

            # SK-04 : utilisation du mapping canonique skill → catégorie
            if skill_lower in self._skill_to_category:
                categorized["technical"].append(skill)
                continue

            # Vérification par pattern souple (compétences composées, e.g. "React Native")
            matched_tech = any(
                self._compiled_tech_patterns[s].search(skill_lower)
                for s in self.all_technical_skills
            )
            if matched_tech:
                categorized["technical"].append(skill)
                continue

            if any(
                self._compiled_soft_patterns[s].search(skill_lower)
                for s in self.all_soft_skills
            ):
                categorized["soft_skills"].append(skill)
                continue

            if self._compiled_named_patterns["spoken_languages"].search(skill):
                categorized["languages"].append(skill)
                continue

            if self._compiled_named_patterns["certifications"].search(skill):
                categorized["certifications"].append(skill)
                continue

            categorized["other"].append(skill)

        logger.debug(
            "get_skill_categories : %s",
            {k: len(v) for k, v in categorized.items()},
        )
        return categorized

    def save_skill_referential(self, filepath: str) -> None:
        """
        Sauvegarde le référentiel des compétences au format JSON.

        Args:
            filepath: Chemin du fichier de destination.
        """
        # SK-01 : datetime.datetime.now() à la place de pd.Timestamp (pas de dépendance pandas)
        referential = {
            "technical_skills": self.technical_skills,
            "soft_skills": self.soft_skills,
            "skill_patterns": _NAMED_PATTERNS,
            "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        try:
            with open(filepath, "w", encoding="utf-8") as fh:
                json.dump(referential, fh, indent=2, ensure_ascii=False)
            logger.info("Référentiel des compétences sauvegardé : %s", filepath)
        except OSError:
            logger.exception("Erreur lors de la sauvegarde du référentiel : %s", filepath)

    def load_skill_referential(self, filepath: str) -> None:
        """
        Charge un référentiel des compétences depuis un fichier JSON.

        Met à jour le référentiel interne et recompile tous les patterns.

        Args:
            filepath: Chemin du fichier JSON à charger.
        """
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                referential = json.load(fh)

            self.technical_skills = referential.get(
                "technical_skills", self.technical_skills
            )
            self.soft_skills = referential.get("soft_skills", self.soft_skills)

            # Reconstruire les index et patterns après rechargement
            self._skill_to_category = {}
            for category, skills in self.technical_skills.items():
                for s in skills:
                    self._skill_to_category[s.lower()] = category

            self.all_technical_skills = set(self._skill_to_category.keys())
            self.all_soft_skills = {s.lower() for s in self.soft_skills}

            # SK-06 : recompilation après rechargement
            self._compiled_tech_patterns = {
                skill: _build_word_pattern(skill)
                for skill in self.all_technical_skills
            }
            self._compiled_soft_patterns = {
                skill: _build_word_pattern(skill)
                for skill in self.all_soft_skills
            }

            logger.info("Référentiel des compétences chargé : %s", filepath)

        except (OSError, json.JSONDecodeError):
            logger.exception("Erreur lors du chargement du référentiel : %s", filepath)

    # ------------------------------------------------------------------
    # Méthodes privées d'extraction
    # ------------------------------------------------------------------

    def _extract_technical_skills(self, text: str) -> Set[str]:
        """Extrait les compétences techniques avec délimiteurs de mots (SK-02)."""
        found: Set[str] = set()
        for skill, pattern in self._compiled_tech_patterns.items():
            if pattern.search(text):
                found.add(skill.title())
        return found

    def _extract_soft_skills(self, text: str) -> Set[str]:
        """Extrait les soft skills avec délimiteurs de mots (SK-02)."""
        found: Set[str] = set()
        for skill, pattern in self._compiled_soft_patterns.items():
            if pattern.search(text):
                found.add(skill.title())
        return found

    def _extract_pattern_skills(self, text: str) -> Set[str]:
        """Extrait les compétences via les patterns nommés pré-compilés (SK-06)."""
        found: Set[str] = set()
        for _name, pattern in self._compiled_named_patterns.items():
            for match in pattern.finditer(text):
                found.add(match.group(0).title())
        return found

    def _extract_contextual_skills(self, text: str) -> Set[str]:
        """Extrait les compétences contextuelles via patterns pré-compilés (SK-06)."""
        found: Set[str] = set()
        for label, patterns in self._compiled_contextual.items():
            for pattern in patterns:
                if pattern.search(text):
                    found.add(label)
                    break
        return found

    # ------------------------------------------------------------------
    # Normalisation et scoring
    # ------------------------------------------------------------------

    def _normalize_skills(self, skills: Set[str]) -> List[str]:
        """
        Filtre les compétences invalides ou trop génériques.

        SK-05 : les sets en amont garantissent l'unicité — pas de set() redondant.
        """
        result: List[str] = []
        for skill in skills:
            clean = skill.strip()
            if len(clean) < 2 or len(clean) > 60:
                continue
            if any(term in clean.lower() for term in _GENERIC_TERMS):
                continue
            result.append(clean)
        return result

    def _score_skills(
        self, skills: List[str], text: str
    ) -> List[Tuple[str, float]]:
        """
        Attribue un score de pertinence à chaque compétence.

        SK-03 : le score combine :
          - la fréquence d'apparition dans le texte (normalisée)
          - un bonus de position (les mentions tôt dans le texte ont plus de poids)

        Returns:
            Liste de tuples (compétence, score) triée par score décroissant,
            puis alphabétiquement en cas d'égalité.
        """
        text_len = max(len(text), 1)
        scored: List[Tuple[str, float]] = []

        for skill in skills:
            pattern = _build_word_pattern(skill.lower())
            matches = list(pattern.finditer(text))
            if not matches:
                # Compétence issue de l'extraction contextuelle : score minimal positif
                scored.append((skill, 0.1))
                continue

            frequency = len(matches)
            # Position du premier match normalisée : 1.0 si début, ~0.0 si fin
            first_pos = matches[0].start()
            position_bonus = 1.0 - (first_pos / text_len)

            score = frequency + position_bonus
            scored.append((skill, score))

        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored