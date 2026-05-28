"""Database engine and session configuration.

Auto-detects SQLite vs PostgreSQL and applies appropriate
compatibility settings.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.types import configure_engine

# Create engine
engine = create_engine(settings.database_url, pool_pre_ping=True)

# Apply database-specific configuration (SQLite PRAGMAs, type compiles)
configure_engine(engine)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
