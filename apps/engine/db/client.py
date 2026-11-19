import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://trader:trader@localhost:5432/smart_trading")
# Sync URL for SQLAlchemy, with the driver named explicitly. A bare "postgresql://"
# picks SQLAlchemy's DEFAULT driver, which changed from psycopg2 to psycopg (v3) in
# SQLAlchemy 2.1 — and only psycopg2 is in requirements.txt, so an unpinned rebuild
# of the image would fail on the first query.
SYNC_URL = (
    DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    .replace("postgres://", "postgresql://", 1)
    .replace("postgresql://", "postgresql+psycopg2://", 1)
)

engine = create_engine(SYNC_URL, pool_pre_ping=True, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def execute_query(query: str, params: dict = None):
    with engine.connect() as conn:
        result = conn.execute(text(query), params or {})
        conn.commit()
        return result
