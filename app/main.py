"""FastAPI application entrypoint with production hardening."""
from contextlib import asynccontextmanager
import logging

from typing import Optional
from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.routers import health, admin, rag, auth_routes, toolkit, browse, strategy, tools, clusters, foundations, sources, profile
from app.dependencies import get_current_user
from app.models.auth import User
from app.settings import settings
from app.startup import run_startup_validation
from app.middleware import (
    RequestLoggingMiddleware,
    RateLimitMiddleware,
    CSRFProtectionMiddleware,
    setup_logging
)

# Configure logging before anything else
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan with startup validation.

    Validates settings and database connection before accepting traffic.
    Fails fast with clear error messages if configuration is invalid.
    """
    logger.info(f"Starting application in {settings.ENV} environment")

    try:
        # Run comprehensive startup validation
        run_startup_validation()

    except Exception as e:
        logger.error(f"Startup validation failed: {e}")
        logger.error("Application will not start")
        raise

    yield

    logger.info("Shutting down application")


app = FastAPI(
    title="The AI Editorial Toolkit",
    description="The AI Editorial Toolkit Learning Platform",
    version="0.1.0",
    lifespan=lifespan
)

# Add middleware (order matters - last added is executed first)
# 1. Logging (outermost - logs everything)
app.add_middleware(RequestLoggingMiddleware)

# 2. CSRF Protection
app.add_middleware(CSRFProtectionMiddleware)

# 3. Rate Limiting
app.add_middleware(RateLimitMiddleware)

# Templates
templates = Jinja2Templates(directory="app/templates")

# Include routers
app.include_router(health.router)
app.include_router(admin.router)
app.include_router(rag.router)
app.include_router(auth_routes.router)
app.include_router(toolkit.router)
app.include_router(browse.router)
app.include_router(tools.router)
app.include_router(clusters.router)
app.include_router(strategy.router)
app.include_router(foundations.router)
app.include_router(sources.router)
app.include_router(profile.router)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, user: Optional[User] = Depends(get_current_user)):
    """Homepage."""
    from app.services.kit_loader import get_all_clusters, get_cluster_tools, get_kit_stats

    clusters_data = get_all_clusters()
    enriched_clusters = []
    for c in clusters_data:
        tool_list = get_cluster_tools(c["slug"])
        enriched_clusters.append({
            **c,
            "tool_count": len(tool_list),
        })

    stats = get_kit_stats()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
            "title": "Grounded",
            "clusters": enriched_clusters,
            "stats": stats,
        }
    )
