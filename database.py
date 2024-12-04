# database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import yaml

def load_config(config_path='config.yaml'):
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

config = load_config()
DATABASE_URL = config['database']['url']

engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)