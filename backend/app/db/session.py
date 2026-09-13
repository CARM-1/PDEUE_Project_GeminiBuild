import os
import pathlib
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DB_PATH = pathlib.Path(__file__).resolve().parent.parent.parent / "pdeue.db"
DEFAULT_DB_URL = f"sqlite:///{DB_PATH}"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DB_URL)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()