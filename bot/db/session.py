from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from bot.config.settings import get_settings
from bot.db.models import Base
from typing import Generator

settings = get_settings()

engine = create_engine(
    settings.postgres_url,
    pool_pre_ping=True,        # reconnect if connection dropped
    pool_size=5,
    max_overflow=10,
    echo=False,                # set True to log all SQL (useful for debugging)
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    """Create all tables if they don't exist. Run once on startup."""
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Context manager for DB sessions — always closes cleanly."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()