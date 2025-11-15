-- Création de la base de données pour la plateforme d'emploi au Sénégal
-- Auteur: Data Engineering Team
-- Date: 2025

-- Activer les extensions nécessaires
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Table: offres_emploi_brutes (table de consolidation des spiders)
CREATE TABLE IF NOT EXISTS offres_emploi_brutes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    spider_source VARCHAR(255) NOT NULL, -- 'emploi', 'senjob', 'emploi_expatDakar'
    original_id VARCHAR(255) NOT NULL,
    title TEXT ,
    url TEXT,
    location VARCHAR(255),
    company_name VARCHAR(255),
    posted_date DATE,
    source VARCHAR(100),
    description TEXT,
    contract_type TEXT,
    salary TEXT,
    category TEXT,
    sector TEXT,
    experience_level TEXT,
    education_level TEXT,
    nb_positions INTEGER DEFAULT 1,
    expiration_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(spider_source, original_id)
);

-- Table: offres_emploi_enrichies (données enrichies par NLP)
CREATE TABLE IF NOT EXISTS offres_emploi_enrichies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    offre_id UUID REFERENCES offres_emploi_brutes(id) ON DELETE CASCADE,
    -- Informations extraites par NLP
    extracted_salary_min INTEGER,
    extracted_salary_max INTEGER,
    extracted_salary_currency VARCHAR(10),
    extracted_contract_type VARCHAR(50),
    extracted_experience_years INTEGER,
    extracted_skills TEXT[], -- Array de compétences
    extracted_sector VARCHAR(100),
    extracted_job_category VARCHAR(100),
    -- Analyse sémantique
    sentiment_score FLOAT,
    key_phrases TEXT[],
    -- Classification
    job_level VARCHAR(50), -- 'Junior', 'Senior', 'Lead', etc.
    job_type VARCHAR(50), -- 'Full-time', 'Part-time', 'Remote', etc.
    -- Métadonnées
    processing_version VARCHAR(20),
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    confidence_score FLOAT
);

-- Table: competences_referentiel (référentiel des compétences)
CREATE TABLE IF NOT EXISTS competences_referentiel (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    competence_name VARCHAR(255) UNIQUE NOT NULL,
    category VARCHAR(100),
    subcategory VARCHAR(100),
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: job_statistics (statistiques calculées)
CREATE TABLE IF NOT EXISTS job_statistics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    metric_name VARCHAR(100) NOT NULL,
    metric_value JSONB NOT NULL,
    period_start DATE,
    period_end DATE,
    category VARCHAR(100),
    location VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: user_profiles (pour les recommandations)
CREATE TABLE IF NOT EXISTS user_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(50),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    location VARCHAR(255),
    experience_years INTEGER,
    education_level VARCHAR(100),
    skills TEXT[],
    preferred_contract_type VARCHAR(50)[],
    preferred_salary_min INTEGER,
    preferred_salary_max INTEGER,
    cv_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: job_recommendations (recommandations générées)
CREATE TABLE IF NOT EXISTS job_recommendations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES user_profiles(id) ON DELETE CASCADE,
    job_id UUID REFERENCES offres_emploi_enrichies(id) ON DELETE CASCADE,
    match_score FLOAT NOT NULL,
    match_reasons TEXT[],
    is_viewed BOOLEAN DEFAULT FALSE,
    is_applied BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index pour améliorer les performances
CREATE INDEX IF NOT EXISTS idx_offres_brutes_source ON offres_emploi_brutes(spider_source);
CREATE INDEX IF NOT EXISTS idx_offres_brutes_date ON offres_emploi_brutes(posted_date);
CREATE INDEX IF NOT EXISTS idx_offres_brutes_location ON offres_emploi_brutes(location);
CREATE INDEX IF NOT EXISTS idx_offres_brutes_contract ON offres_emploi_brutes(contract_type);
CREATE INDEX IF NOT EXISTS idx_offres_enrichies_salary ON offres_emploi_enrichies(extracted_salary_min, extracted_salary_max);
CREATE INDEX IF NOT EXISTS idx_offres_enrichies_skills ON offres_emploi_enrichies USING GIN(extracted_skills);
CREATE INDEX IF NOT EXISTS idx_job_statistics_period ON job_statistics(period_start, period_end);

-- Fonction pour mettre à jour le timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_offres_emploi_brutes_updated_at ON offres_emploi_brutes;
DROP TRIGGER IF EXISTS update_user_profiles_updated_at ON user_profiles;

-- Triggers pour automatiquement mettre à jour updated_at
CREATE TRIGGER update_offres_emploi_brutes_updated_at BEFORE UPDATE ON offres_emploi_brutes 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER  update_user_profiles_updated_at BEFORE UPDATE ON user_profiles 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Vue pour les analyses rapides
CREATE OR REPLACE VIEW job_market_overview AS
SELECT 
    DATE_TRUNC('month', posted_date) as month,
    COUNT(*) as total_offers,
    COUNT(DISTINCT company_name) as unique_companies,
    COUNT(DISTINCT location) as unique_locations,
    AVG(extracted_salary_min) as avg_salary_min,
    AVG(extracted_salary_max) as avg_salary_max,
    mode() WITHIN GROUP (ORDER BY contract_type) as most_common_contract,
    mode() WITHIN GROUP (ORDER BY extracted_sector) as most_common_sector
FROM offres_emploi_brutes b
LEFT JOIN offres_emploi_enrichies e ON b.id = e.offre_id
WHERE posted_date >= CURRENT_DATE - INTERVAL '12 months'
GROUP BY DATE_TRUNC('month', posted_date)
ORDER BY month DESC;


-- Migration pour ajouter les champs d'authentification à la table user_profiles
-- À exécuter sur votre base de données PostgreSQL

-- Ajouter les nouveaux champs
ALTER TABLE user_profiles 
ADD COLUMN IF NOT EXISTS hashed_password VARCHAR(255),
ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE,
ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS verification_token VARCHAR(255),
ADD COLUMN IF NOT EXISTS reset_password_token VARCHAR(255),
ADD COLUMN IF NOT EXISTS reset_password_expires TIMESTAMP,
ADD COLUMN IF NOT EXISTS last_login TIMESTAMP;

-- Mettre à jour les contraintes
ALTER TABLE user_profiles 
ALTER COLUMN hashed_password SET NOT NULL;

-- Ajouter des index pour les performances
CREATE INDEX IF NOT EXISTS idx_user_profiles_verification_token ON user_profiles(verification_token);
CREATE INDEX IF NOT EXISTS idx_user_profiles_reset_token ON user_profiles(reset_password_token);
CREATE INDEX IF NOT EXISTS idx_user_profiles_is_active ON user_profiles(is_active);

-- Commentaires
COMMENT ON COLUMN user_profiles.hashed_password IS 'Mot de passe hashé avec bcrypt';
COMMENT ON COLUMN user_profiles.is_active IS 'Indique si le compte est actif';
COMMENT ON COLUMN user_profiles.is_verified IS 'Indique si l''email a été vérifié';
COMMENT ON COLUMN user_profiles.verification_token IS 'Token pour la vérification d''email';
COMMENT ON COLUMN user_profiles.reset_password_token IS 'Token pour la réinitialisation de mot de passe';
COMMENT ON COLUMN user_profiles.reset_password_expires IS 'Date d''expiration du token de réinitialisation';
COMMENT ON COLUMN user_profiles.last_login IS 'Date de dernière connexion';