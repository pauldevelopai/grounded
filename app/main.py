"""FastAPI application entrypoint."""
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import logging

from app.config import settings
from app.database import engine, Base, SessionLocal
from app.models.user import User
from app.auth.password import hash_password

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_admin_user():
    """Create admin user if it doesn't exist."""
    db = SessionLocal()
    try:
        # Check if admin user exists
        admin = db.query(User).filter(User.email == settings.ADMIN_EMAIL).first()
        if not admin:
            logger.info(f"Creating admin user: {settings.ADMIN_EMAIL}")
            admin = User(
                email=settings.ADMIN_EMAIL,
                password_hash=hash_password(settings.ADMIN_PASSWORD),
                is_admin=True
            )
            db.add(admin)
            db.commit()
            logger.info("Admin user created successfully")
        else:
            logger.info("Admin user already exists")
    except Exception as e:
        logger.error(f"Error creating admin user: {e}")
        db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting ToolkitRAG application...")
    logger.info(f"Environment: {settings.APP_ENV}")
    logger.info(f"Database: {settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'configured'}")

    # Create admin user if doesn't exist
    try:
        create_admin_user()
    except Exception as e:
        logger.warning(f"Could not create admin user (database may not be ready): {e}")

    yield

    logger.info("Shutting down ToolkitRAG application...")


# Create FastAPI app
app = FastAPI(
    title="ToolkitRAG",
    description="AI Toolkit Learning & Decision Support Platform",
    version="0.1.0",
    lifespan=lifespan
)

# Templates
templates = Jinja2Templates(directory="app/templates")


# Health endpoints
@app.get("/health")
async def health():
    """Basic health check."""
    return {"status": "healthy"}


@app.get("/ready")
async def ready():
    """Readiness check."""
    # TODO: Check database connection
    # TODO: Check if embeddings exist
    return {"status": "ready", "database": "connected"}


# Import dependencies before root endpoint
from app.auth.dependencies import get_current_user_optional

# Root endpoint
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, current_user: User = Depends(get_current_user_optional)):
    """Home page."""
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "title": "ToolkitRAG", "user": current_user}
    )


# Import and include routers
from app.routers import auth, pages

app.include_router(auth.router)
app.include_router(pages.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
