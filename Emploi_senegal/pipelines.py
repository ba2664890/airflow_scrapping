import psycopg2
import hashlib
import re
from datetime import datetime, timedelta
import scrapy
from scrapy.exceptions import DropItem
from psycopg2.extras import execute_values


def clean_list(value):
    if isinstance(value, list):
        return str(value[0]).strip() if value else None
    return str(value).strip() if value else None

def clean_int(value):
    try:
        return int(re.sub(r'\D', '', str(value).strip()))
    except (ValueError, AttributeError):
        return None

def clean_float(value):
    try:
        return float(re.search(r'(\d+(?:\.\d+)?)', str(value).replace('\u202f', '').replace(' ', '')).group(1))
    except (ValueError, AttributeError):
        return None

def process_item(self, item, spider):
    # on flush à chaque fois
    self.buffer.append({k: item.get(k) for k in self.fields})
    self._flush()
    return item

class DuplicatesPipeline:
    def __init__(self):
        self.urls_seen = set()

    def process_item(self, item, spider):
        url_raw = item["url"][0] if isinstance(item["url"], list) else item["url"]
        url_hash = hashlib.md5(url_raw.encode()).hexdigest()
        if url_hash in self.urls_seen:
            raise DropItem(f"URL déjà traitée : {url_raw}")
        self.urls_seen.add(url_hash)
        # ➜ on ne touche pas à item, on renvoie juste l’item tel quel
        return item
    
class DuplicatesPipeline:
    def __init__(self):
        self.urls_seen = set()

    def process_item(self, item, spider):
        url_raw = item["url"][0] if isinstance(item["url"], list) else item["url"]
        url_hash = hashlib.md5(url_raw.encode()).hexdigest()
        if url_hash in self.urls_seen:
            raise DropItem(f"URL déjà traitée : {url_raw}")
        self.urls_seen.add(url_hash)
        item["id"] = url_hash      # ← on remet cette ligne
        return item

# ------------------------------------------------------------------
# Pipeline JOBS – emploisenegal.com
# ------------------------------------------------------------------
from .model import Emploi
class EmploiSenegalPostgreSQLPipeline:
    def __init__(self, database, user, password, host, port):
        self.db_params = dict(database=database, user=user, password=password, host=host, port=port)
        self.batch_size = 1          # ← flush immédiat
        self.buffer = []
        self.fields = ["id", "url", "title", "company_name", "company_sectors", "description",
                       "contract", "region", "education", "experience",
                       "skills", "posted", "source", "scraped_at", "metier_type", "metiers", "job_missions", "job_profile", "job_criteria", "job_skills", "job_count"]
    # ---------- vie du spider ----------
    def open_spider(self, spider):
        self.conn = psycopg2.connect(**self.db_params)
        self._ensure_table()
        spider.logger.info("[PG-REALTIME] connecté → %s", self.db_params["database"])

    def close_spider(self, spider):
        if self.buffer:
            self._flush(spider)

    def process_item(self, item, spider):
        # on met dans le buffer et on flush tout de suite
        self.buffer.append({k: item.get(k) for k in self.fields})
        self._flush(spider)
        return item

    @classmethod
    def from_crawler(cls, crawler):
        db = crawler.settings.getdict("DATABASE")
        return cls(
            database=db["database"],
            user=db["user"],
            password=db["password"],
            host=db["host"],
            port=db["port"],
        )
    # ---------- SQL ----------
    def _ensure_table(self):
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS jobs_emploi_senegal(
                    id VARCHAR(32) PRIMARY KEY, url TEXT UNIQUE, title TEXT,
                    company_name TEXT, company_sectors TEXT, description TEXT, contract TEXT, region TEXT,
                    education TEXT, experience TEXT, skills TEXT, posted DATE, metiers TEXT, metier_type TEXT,
                    source TEXT, scraped_at TIMESTAMP DEFAULT NOW(),
                    job_missions TEXT, job_profile TEXT, job_criteria TEXT, job_skills TEXT, job_count TEXT
                );
            """)
            self.conn.commit()

    def _flush(self, spider):
        if not self.buffer:
            return
        # complétion clés manquantes
        required = {"id", "url", "title", "company", "description",
                    "contract", "region", "education", "experience",
                    "skills", "posted", "source", "scraped_at"}
        for row in self.buffer:
            for k in required:
                row.setdefault(k, None)

        with self.conn.cursor() as cur:
            for row in self.buffer:
                cur.execute("""
                    INSERT INTO jobs_emploi_senegal(
                        id, url, title, company_name, company_sectors, metier_type, metiers, description,
                        contract, region, education, experience,
                        skills, posted, source, scraped_at, job_missions, job_profile, job_criteria, job_skills, job_count
                    )
                    VALUES (
                        %(id)s, %(url)s, %(title)s, %(company_name)s, %(company_sectors)s, %(metier_type)s, %(metiers)s,
                        %(description)s, %(contract)s, %(region)s,
                        %(education)s, %(experience)s, %(skills)s,
                        %(posted)s, %(source)s, %(scraped_at)s, %(job_missions)s, %(job_profile)s, %(job_criteria)s, %(job_skills)s, %(job_count)s
                    )
                    ON CONFLICT (url) DO UPDATE
                    SET title       = EXCLUDED.title,
                        company_name = EXCLUDED.company_name,
                        company_sectors = EXCLUDED.company_sectors,
                        description = EXCLUDED.description,
                        contract    = EXCLUDED.contract,
                        region      = EXCLUDED.region,
                        education   = EXCLUDED.education,
                        experience  = EXCLUDED.experience,
                        skills      = EXCLUDED.skills,
                        posted      = EXCLUDED.posted,
                        scraped_at  = EXCLUDED.scraped_at;
                """, row)
                # ---------- LOG TEMPS REEL ----------
                spider.logger.info("[PG-INSERT] %s", row["url"])
            self.conn.commit()
        self.buffer.clear()





# ------------------------------------------------------------------
# Pipeline JOBS – emploiedakar.com
# ------------------------------------------------------------------


from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .model import Base, Emploi
from datetime import datetime


class SQLAlchemyPipeline:
    def __init__(self):
        # Met à jour ton URI PostgreSQL avec user/password corrects
        self.engine = create_engine(
            "postgresql://neondb_owner:npg_dMZCO35gNoeP@ep-long-resonance-a4y4jpe4-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require",
            pool_pre_ping=True
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

    def process_item(self, item, spider):
        # description
        if isinstance(item.get("description"), list):
            item["description"] = "\n".join([d.strip() for d in item["description"] if d.strip()])

        # location
        if isinstance(item.get("location"), list):
            item["location"] = ", ".join([l.strip() for l in item["location"] if l.strip()])

        # posted_date
        if isinstance(item.get("posted_date"), list) and item.get("posted_date"):
            date_str = item["posted_date"][0].strip()
            try:
                item["posted_date"] = datetime.strptime(date_str, "%Y-%m-%d").date()  # adapter le format réel
            except ValueError:
                item["posted_date"] = None
        elif isinstance(item.get("posted_date"), str):
            try:
                item["posted_date"] = datetime.strptime(item["posted_date"], "%Y-%m-%d").date()
            except ValueError:
                item["posted_date"] = None
        else:
            item["posted_date"] = None


        # title, url, source
        for field in ["title", "url", "source", "company_name", "location", "contract_type"]:
            val = item.get(field)
            if isinstance(val, list):
                item[field] = val[0]  # prend le premier élément


        emploi = Emploi(
            id=item["id"],
            title=item.get("title"),        # string
            url=item.get("url"),            # string
            location=item.get("location"),  # string
            posted_date=item.get("posted_date"),  # date
            source=item.get("source"),      # string
            description_p=item.get("description_p"),  # string
            description_ul=item.get("description_ul"),  # string
            company_name=item.get("company_name"),  # string
            contract_type=item.get("contract_type")  # string

        )


        try:
            self.session.merge(emploi)
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            spider.logger.error(f"Erreur insertion : {e}")

        return item


# ------------------------------------------------------------------
# Pipeline JOBS – senjob.com
# ------------------------------------------------------------------

from .model import senjob

class senjobPipeline():
    def __init__(self):
        # Met à jour ton URI PostgreSQL avec user/password corrects
        self.engine = create_engine(
            "postgresql://neondb_owner:npg_dMZCO35gNoeP@ep-long-resonance-a4y4jpe4-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require",
            pool_pre_ping=True
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

    def process_item(self, item, spider):
        # description
        if isinstance(item.get("description"), list):
            item["description"] = "\n".join([d.strip() for d in item["description"] if d.strip()])

        # location
        if isinstance(item.get("location"), list):
            item["location"] = ", ".join([l.strip() for l in item["location"] if l.strip()])


        # title, url, source
        for field in ["title", "url", "source", "company_name"]:
            val = item.get(field)
            if isinstance(val, list):
                item[field] = val[0]  # prend le premier élément


        emploi = senjob(
            id=item["id"],
            title=item.get("title"),        # string
            url=item.get("url"),            # string
            location=item.get("location"),  # string
            posted_date=item.get("posted_date"),  # date
            categorie=item.get("categorie"),  # string
            source=item.get("source"),      # string
            description=item.get("description"),  # string
            salaire=item.get("salaire"),  # string
            expiration=item.get("expiration"),  # string
            contract_type=item.get("contract_type")  # string

        )


        try:
            self.session.merge(emploi)
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            spider.logger.error(f"Erreur insertion : {e}")

        return item


# ------------------------------------------------------------------
# Pipeline JOBS – emploi_expatdakar.com
# ------------------------------------------------------------------
# Pipeline pour expat-dakar
from .model import emploi_expatdakar
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

class ExpatDakarPipeline:
    def __init__(self):
        self.engine = create_engine("postgresql://neondb_owner:npg_dMZCO35gNoeP@ep-long-resonance-a4y4jpe4-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require", pool_pre_ping=True)
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
    def open_spider(self, spider):
        self.session = self.Session()
    
    def close_spider(self, spider):
        self.session.close()

    import re
    from datetime import datetime, timedelta

    def clean_posted_date(self, date_str):
        if not date_str:
            return None

        date_str = date_str.strip().lower()

        # Cas 1️⃣ : format standard ISO (YYYY-MM-DD)
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            pass

        # Cas 2️⃣ : "vendredi 1118" ou "vendredi, 11:18"
        # → On prend la date du jour avec heure si possible
        match = re.search(r"\b(\d{1,2})([:h]?)(\d{2})?\b", date_str)
        if match:
            try:
                hour = int(match.group(1))
                minute = int(match.group(3)) if match.group(3) else 0
                now = datetime.now().replace(second=0, microsecond=0)
                return now.replace(hour=hour, minute=minute)
            except Exception:
                pass

        # Cas 3️⃣ : "il y a X jours"
        match = re.search(r"il y a (\d+) jours?", date_str, re.IGNORECASE)
        if match:
            days_ago = int(match.group(1))
            return datetime.now() - timedelta(days=days_ago)

        # Cas 4️⃣ : "hier"
        if "hier" in date_str:
            return datetime.now() - timedelta(days=1)
        
        # 🧩 Cas 3 : format "30. août, 12:19" ou "28. juil., 13:49"
        mois_fr = {
            "janv": 1, "févr": 2, "fevr": 2, "mars": 3, "avr": 4,
            "mai": 5, "juin": 6, "juil": 7, "août": 8, "aout": 8,
            "sept": 9, "oct": 10, "nov": 11, "déc": 12, "dec": 12
        }

        match = re.match(r"(\d{1,2})\.\s*([a-zéû]+)", date_str)
        if match:
            jour = int(match.group(1))
            mois_txt = match.group(2)[:4]  # ex: "août" → "août"
            mois = mois_fr.get(mois_txt.replace('.', ''), None)
            if mois:
                annee = datetime.now().year
                try:
                    return datetime(annee, mois, jour)
                except ValueError:
                    pass

        # Cas 5️⃣ : format non reconnu → None
        return None

    

    def process_item(self, item, spider):
        import re
        def clean(val):
            if isinstance(val, list):
                val = val[0]
            if isinstance(val, str):
                val = val.strip()
                val = re.sub(r"\s+", " ", val)  # supprime espaces multiples
                val = re.sub(r"[\r\n\t]", "", val)  # supprime retours ligne/tab
                val = re.sub(r"[^\w\sÀ-ÿ&'-]", "", val)  # supprime caractères spéciaux sauf lettres, chiffres, espace, accentués, &, ', -
            return val
        for field in ["title", "source", "posted_date", "location","region", "description", "type_contrat", "employeur", "secteur", "niveau", "niveau_etude", "experience", "nb_postes"]:
            if field != "description":  # description peut être long, on ne la nettoie pas trop
                item[field] = clean(item.get(field))
            else:
                val = item.get(field)
                if isinstance(val, list):
                    val = val[0]
                item[field] = val
        item["posted_date"] = self.clean_posted_date(item.get("posted_date"))
        expat = emploi_expatdakar(
            id=item.get('id'),
            title=item.get('title'),
            posted_date=item.get('posted_date'),
            ad_id=item.get('ad_id'),
            location=item.get('location'),
            region=item.get('region'),
            employeur=item.get('employeur'),
            secteur=item.get('secteur'),
            type_contrat=item.get('type_contrat'),
            niveau=item.get('niveau'),
            niveau_etude=item.get('niveau_etude'),
            experience=item.get('experience'),
            nb_postes=item.get('nb_postes'),
            description=item.get('description'),
            url=item.get('url'),
            source=item.get('source'),
        )
        try:
            self.session.merge(expat)
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            spider.logger.error(f"Erreur insertion expat-dakar : {e}")
        return item



# ------------------------------------------------------------------
# Pipeline JOBS – concoursn.com
# ------------------------------------------------------------------
from .model import concoursn_stage
import json
from datetime import datetime, timedelta
import re

class ConcoursnPipeline:
    def __init__(self):
        self.engine = create_engine(
            "postgresql://neondb_owner:npg_dMZCO35gNoeP@ep-long-resonance-a4y4jpe4-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require",
            pool_pre_ping=True
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
    
    def open_spider(self, spider):
        self.session = self.Session()
    
    def close_spider(self, spider):
        self.session.close()

    def parse_relative_date(self, date_str):
        """Convertit les dates relatives comme 'depuis 18 minutes' en datetime"""
        if not date_str:
            return None
        
        date_str = date_str.lower().strip()
        now = datetime.now()
        
        # Patterns de date relative
        patterns = {
            r'(\d+)\s+(?:minute|min)s?': lambda m: now - timedelta(minutes=int(m.group(1))),
            r'(\d+)\s+(?:heure|h)s?': lambda m: now - timedelta(hours=int(m.group(1))),
            r'(\d+)\s+(?:jour|j)s?': lambda m: now - timedelta(days=int(m.group(1))),
            r'hier': lambda m: now - timedelta(days=1),
            r'aujourd\'hui': lambda m: now,
        }

        for pattern, func in patterns.items():
            match = re.search(pattern, date_str, re.IGNORECASE)
            if match:
                return func(match)
        
        # Si format date absolu (ex: "08 Décembre 2025")
        try:
            return datetime.strptime(date_str, "%d %B %Y")
        except:
            pass
        
        return None

    def process_item(self, item, spider):
        # Nettoyage de la description
        if isinstance(item.get("description"), list):
            item["description"] = "\n".join([d.strip() for d in item["description"] if d.strip()])
        
        # Conversion des listes en JSON strings
        for field in ["categories", "tags"]:
            if isinstance(item.get(field), list):
                item[field] = json.dumps([f.strip() for f in item[field] if f.strip()], ensure_ascii=False)

        # Parsing de la date
        item["posted_date"] = self.parse_relative_date(item.get("posted_date_raw"))
        
        # Génération de l'ID unique basé sur l'URL
        item["id"] = hashlib.md5(item["url"].encode()).hexdigest()
        
        # Date de scraping
        item["scraped_at"] = datetime.utcnow()

        # Création de l'objet
        stage = concoursn_stage(
            id=item["id"],
            title=item.get("title"),
            url=item.get("url"),
            source=item.get("source"),
            categories=item.get("categories"),
            tags=item.get("tags"),
            posted_date=item.get("posted_date"),
            description=item.get("description"),
            company=item.get("company"),
            scraped_at=item.get("scraped_at")
        )

        try:
            self.session.merge(stage)
            self.session.commit()
            spider.logger.info(f"[CONCOURSNS-INSERT] {item['url']}")
        except Exception as e:
            self.session.rollback()
            spider.logger.error(f"Erreur insertion concoursn : {e}")
        
        return item