"""Health check endpoints."""
from fastapi import APIRouter, Depends, status, Response
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    """
    Basic health check - process is alive.

    Returns 200 if the application is running.
    Used by load balancers and monitoring systems.
    """
    return {"status": "healthy"}


@router.get("/ready")
async def ready(response: Response, db: Session = Depends(get_db)):
    """
    Readiness check - verifies database connectivity and required tables.

    Returns 200 if ready to accept traffic, 503 if not ready.
    Used by orchestrators to know when to route traffic to this instance.
    """
    try:
        # Test database connection
        with db.connection() as conn:
            conn.execute(text("SELECT 1"))

        # Check for key tables
        required_tables = ['users', 'toolkit_documents', 'toolkit_chunks']
        with db.connection() as conn:
            # Build the IN clause with proper escaping
            table_list = ','.join(f"'{t}'" for t in required_tables)
            result = conn.execute(
                text(
                    f"SELECT tablename FROM pg_tables "
                    f"WHERE schemaname = 'public' "
                    f"AND tablename IN ({table_list})"
                )
            )
            existing_tables = {row[0] for row in result}

        missing_tables = set(required_tables) - existing_tables

        if missing_tables:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {
                "status": "not_ready",
                "database": "connected",
                "tables": "missing",
                "missing_tables": list(missing_tables),
                "message": "Run migrations: alembic upgrade head"
            }

        return {
            "status": "ready",
            "database": "connected",
            "tables": "present"
        }

    except Exception as e:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "database": "disconnected",
            "error": str(e),
            "message": "Database connection failed"
        }
