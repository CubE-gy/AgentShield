from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base
from app.settings import Settings

settings = Settings()

engine = create_engine(settings.dev_database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    autocommit=False,
)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)