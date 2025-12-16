import datetime
from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Emploi(Base):
    __tablename__ = "emplois"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=True)
    url = Column(String, nullable=True)
    location = Column(String, nullable=True)
    company_name = Column(String, nullable=True)
    posted_date = Column(String, nullable=False)
    source = Column(String, nullable=True)
    description_p = Column(Text, nullable=True)  # <--- text long
    description_ul = Column(Text, nullable=True)  # <--- text long
    contract_type = Column(String, nullable=True)


class senjob(Base):
    __tablename__ = "senjobs"

    id = Column(String, primary_key=True)
    title = Column(Text, nullable=True)
    url = Column(String, nullable=True)
    location = Column(String, nullable=True)
    posted_date = Column(String, nullable=True)
    source = Column(String, nullable=True)
    description = Column(Text, nullable=True)  # <--- text long
    expiration = Column(Text, nullable=True)  # <--- text long
    salaire = Column(String, nullable=True)
    categorie = Column(String, nullable=True)
    contract_type = Column(String, nullable=True)

    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}



class emploi_expatdakar(Base):
    __tablename__ = "emploi_expatdakar"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=True)
    posted_date = Column(String, nullable=True)
    ad_id = Column(String, nullable=True)
    location = Column(String, nullable=True)
    region = Column(String, nullable=True)
    employeur = Column(String, nullable=True)
    secteur = Column(String, nullable=True)
    type_contrat = Column(String, nullable=True)
    niveau = Column(String, nullable=True)
    niveau_etude = Column(String, nullable=True)
    experience = Column(String, nullable=True)
    nb_postes = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    url = Column(String, nullable=True)
    source = Column(String, nullable=True)
    
class concoursn_stage(Base):
    __tablename__ = "concoursn_stages"
    
    id = Column(String, primary_key=True)
    title = Column(String, nullable=True)
    url = Column(String, unique=True, nullable=True)
    source = Column(String, nullable=True)
    categories = Column(String, nullable=True)  # JSON ou texte séparé par virgules
    tags = Column(String, nullable=True)        # JSON ou texte séparé par virgules
    posted_date = Column(DateTime, nullable=True)
    description = Column(Text, nullable=True)
    company = Column(String, nullable=True)
    scraped_at = Column(DateTime, default=datetime.utcnow)