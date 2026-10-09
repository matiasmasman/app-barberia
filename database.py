from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# URL de conexión al contenedor Docker: postgresql://usuario:password@host:puerto/nombre_bd
SQLALCHEMY_DATABASE_URL = "postgresql+psycopg2://postgres:admin123@localhost:5432/saas_turnos"

engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()