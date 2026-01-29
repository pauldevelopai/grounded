"""FastAPI application entrypoint with production hardening."""
from contextlib import asynccontextmanager
import logging

from typing import Optional
from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse

from app.routers import health, admin, rag, auth_routes, toolkit, browse, strategy, tools, clusters, foundations, sources, profile, feedback, reviews, discovery, playbook, recommendations
from app.dependencies import get_current_user
from app.db import get_db
from app.models.auth import User
from app.settings import settings
from app.startup import run_startup_validation
from app.products.definitions import register_all_products
from app.templates_engine import templates
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

        # Register all products and editions
        register_all_products()
        logger.info("Products and editions registered successfully")

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
app.include_router(feedback.router)
app.include_router(reviews.router)
app.include_router(discovery.router)
app.include_router(playbook.router)
app.include_router(recommendations.router)


@app.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    user: Optional[User] = Depends(get_current_user),
    db=Depends(get_db),
):
    """Homepage."""
    from app.services.kit_loader import get_all_clusters, get_cluster_tools, get_kit_stats
    from app.services.recommendation import get_suggested_for_location

    clusters_data = get_all_clusters()
    enriched_clusters = []
    for c in clusters_data:
        tool_list = get_cluster_tools(c["slug"])
        enriched_clusters.append({
            **c,
            "tool_count": len(tool_list),
        })

    stats = get_kit_stats()

    # Get personalized recommendations for logged-in users
    suggested_tools = []
    show_suggested = False
    if user:
        try:
            recs = get_suggested_for_location(db, user, "home")
            # Convert Pydantic models to dicts for Jinja2
            suggested_tools = [r.model_dump() if hasattr(r, 'model_dump') else r for r in recs]
            show_suggested = len(suggested_tools) > 0
        except Exception:
            pass  # Fail gracefully if recommendations unavailable

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
            "title": "Grounded",
            "clusters": enriched_clusters,
            "stats": stats,
            "suggested_tools": suggested_tools,
            "suggested_title": "Suggested for You",
            "show_suggested": show_suggested,
            "suggested_location": "home",
        }
    )
