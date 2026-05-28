"""
Initialize the database for local development (SQLite).

Creates all tables defined in the ORM models.
For PostgreSQL, use `alembic upgrade head` instead.
"""

from app.core.config import settings
from app.db import engine
from app.models import Base


def init_db() -> None:
    """Create all tables if they don't exist."""
    print(f"Connecting to: {settings.database_url}")
    Base.metadata.create_all(bind=engine)
    print("All tables created successfully.")


if __name__ == "__main__":
    init_db()
