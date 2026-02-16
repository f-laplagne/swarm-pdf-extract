import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dashboard.data.models import Base

# Resolve DB path relative to the dashboard directory
_DASHBOARD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DB = os.path.join(_DASHBOARD_DIR, "data", "rationalize.db")


def get_engine(url: str | None = None):
    db_url = url or os.environ.get("DATABASE_URL", f"sqlite:///{_DEFAULT_DB}")
    # Resolve relative sqlite paths from the dashboard directory
    if db_url.startswith("sqlite:///") and not db_url.startswith("sqlite:////"):
        rel_path = db_url.replace("sqlite:///", "")
        if not os.path.isabs(rel_path):
            abs_path = os.path.join(_DASHBOARD_DIR, rel_path)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            db_url = f"sqlite:///{abs_path}"
    return create_engine(db_url, echo=False)


def init_db(engine=None):
    if engine is None:
        engine = get_engine()
    Base.metadata.create_all(engine)
    return engine


def get_session(engine=None):
    if engine is None:
        engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()
