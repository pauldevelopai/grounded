"""FastAPI application entrypoint."""
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import logging

from app.config import settings
from app.database import engine, Base

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting ToolkitRAG application...")
    logger.info(f"Environment: {settings.APP_ENV}")
    logger.info(f"Database: {settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'configured'}")

    # TODO: Create admin user if doesn't exist
    # TODO: Check if toolkit document exists

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


# Root endpoint
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page."""
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "title": "ToolkitRAG"}
    )


# TODO: Import and include routers
# from app.routers import auth, pages, rag, strategy, admin
# app.include_router(auth.router)
# app.include_router(pages.router)
# app.include_router(rag.router)
# app.include_router(strategy.router)
# app.include_router(admin.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
