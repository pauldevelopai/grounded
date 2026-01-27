"""Application startup validation and initialization."""
import logging
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.settings import settings
from app.db import engine

logger = logging.getLogger(__name__)


def validate_settings() -> None:
    """
    Validate all required settings at startup.

    Raises:
        ValueError: If required settings are missing or invalid
    """
    logger.info(f"Validating settings for ENV={settings.ENV}")

    # Run comprehensive validation
    settings.validate_required_for_env()
    settings.validate_embedding_config()

    logger.info("✓ Settings validation passed")


def validate_database() -> None:
    """
    Validate database connection and required tables.

    Raises:
        Exception: If database is unreachable or tables are missing
    """
    logger.info("Validating database connection...")

    try:
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        logger.info("✓ Database connection successful")

        # Check for required tables
        required_tables = [
            'users',
            'sessions',
            'toolkit_documents',
            'toolkit_chunks',
            'chat_logs',
            'feedback'
        ]

        with engine.connect() as conn:
            # Query PostgreSQL system tables
            result = conn.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public'"
                )
            )
            existing_tables = {row[0] for row in result}

        missing_tables = set(required_tables) - existing_tables

        if missing_tables:
            raise ValueError(
                f"Missing required database tables: {', '.join(missing_tables)}. "
                "Run migrations with: alembic upgrade head"
            )

        logger.info(f"✓ All required tables present: {', '.join(required_tables)}")

    except Exception as e:
        logger.error(f"✗ Database validation failed: {e}")
        raise


def run_startup_validation() -> None:
    """
    Run all startup validations.

    This is called during application startup and will fail fast
    with clear error messages if any validation fails.

    Raises:
        Exception: If any validation fails
    """
    logger.info("=" * 60)
    logger.info("Starting application startup validation")
    logger.info("=" * 60)

    try:
        # Validate settings
        validate_settings()

        # Validate database
        validate_database()

        logger.info("=" * 60)
        logger.info("✓ All startup validations passed")
        logger.info("=" * 60)

    except Exception as e:
        logger.error("=" * 60)
        logger.error("✗ Startup validation failed")
        logger.error("=" * 60)
        logger.error(f"Error: {e}")
        logger.error("")
        logger.error("Application will not start until this is resolved.")
        raise
