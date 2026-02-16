import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dashboard.data.models import Base


def get_engine(url: str | None = None):
    db_url = url or os.environ.get("DATABASE_URL", "sqlite:///data/rationalize.db")
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
