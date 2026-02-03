"""FastAPI application entrypoint with production hardening."""
from contextlib import asynccontextmanager
import logging

from typing import Optional
from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse

from app.routers import health, admin, rag, auth_routes, toolkit, strategy, tools, clusters, sources, profile, feedback, reviews, discovery, playbook, recommendations, resources, usecases, foundations
from app.routers.recommendations import page_router as recommendations_pages
from app.routers.discovery import approved_router as approved_tools_router
from app.dependencies import get_current_user
from app.db import get_db
from app.models.auth import User
from app.settings import settings
from app.startup import run_startup_validation
from app.products.definitions import register_all_products
from app.products.guards import FeatureDisabledError, get_feature_disabled_context
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
    title="AI Toolkit",
    description="AI Toolkit - AI Learning Platform",
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


# =============================================================================
# EXCEPTION HANDLERS
# =============================================================================

@app.exception_handler(FeatureDisabledError)
async def feature_disabled_handler(request: Request, exc: FeatureDisabledError):
    """
    Handle FeatureDisabledError by showing a friendly message.

    This is triggered when a user tries to access a feature that is not
    enabled in the current Product + Edition.
    """
    # Get the referer to use as redirect URL, or default to homepage
    referer = request.headers.get("referer", "/")

    context = get_feature_disabled_context(
        request=request,
        feature_name=exc.feature_name,
        redirect_url=referer
    )

    return templates.TemplateResponse(
        "feature_disabled.html",
        context,
        status_code=403
    )


# Include routers
app.include_router(health.router)
app.include_router(admin.router)
app.include_router(rag.router)
app.include_router(auth_routes.router)
app.include_router(toolkit.router)
app.include_router(tools.router)
app.include_router(clusters.router)
app.include_router(strategy.router)
app.include_router(sources.router)
app.include_router(profile.router)
app.include_router(feedback.router)
app.include_router(reviews.router)
app.include_router(discovery.router)
app.include_router(approved_tools_router)  # Approved tools staging area
app.include_router(playbook.router)
app.include_router(recommendations.router)
app.include_router(recommendations_pages)  # For You page at /for-you
app.include_router(resources.router)  # Public resources at /resources
app.include_router(usecases.router)  # Public use cases at /use-cases
app.include_router(foundations.router)  # Foundational content at /foundations


@app.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    user: Optional[User] = Depends(get_current_user),
    db=Depends(get_db),
):
    """Homepage."""
    from app.services.kit_loader import (
        get_all_clusters_with_approved,
        get_cluster_tools,
        get_kit_stats_with_approved,
        get_approved_tools_from_db,
        ADMIN_APPROVED_CLUSTER_SLUG,
    )

    clusters_data = get_all_clusters_with_approved(db)
    enriched_clusters = []
    for c in clusters_data:
        if c["slug"] == ADMIN_APPROVED_CLUSTER_SLUG:
            # Admin-approved cluster already has tool_count set
            enriched_clusters.append(c)
        else:
            tool_list = get_cluster_tools(c["slug"])
            enriched_clusters.append({
                **c,
                "tool_count": len(tool_list),
            })

    stats = get_kit_stats_with_approved(db)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
            "title": "AI Toolkit",
            "clusters": enriched_clusters,
            "stats": stats,
        }
    )


# =============================================================================
# PLACEHOLDER PRODUCT LANDING PAGES
# =============================================================================

@app.get("/audio", response_class=HTMLResponse)
async def audio_landing(
    request: Request,
    user: Optional[User] = Depends(get_current_user),
):
    """Landing page for AI Audio (placeholder product)."""
    from app.products.registry import ProductRegistry

    product = ProductRegistry.get("ai_audio")
    if not product:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Product not found")

    return templates.TemplateResponse(
        "placeholder.html",
        {
            "request": request,
            "user": user,
            "product_name": product.name,
            "product_description": product.description,
            "brand_logo_text": product.branding.logo_text,
            "brand_primary_color": product.branding.primary_color,
            "brand_secondary_color": product.branding.secondary_color,
            "placeholder_features": [
                "AI-powered audio transcription and editing",
                "Voice cloning and text-to-speech tools",
                "Podcast production assistants",
                "Audio enhancement and noise reduction",
                "Multi-language dubbing tools",
            ],
        }
    )


@app.get("/letter-plus", response_class=HTMLResponse)
async def letter_plus_landing(
    request: Request,
    user: Optional[User] = Depends(get_current_user),
):
    """Landing page for Letter+ (placeholder product)."""
    from app.products.registry import ProductRegistry

    product = ProductRegistry.get("letter_plus")
    if not product:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Product not found")

    return templates.TemplateResponse(
        "placeholder.html",
        {
            "request": request,
            "user": user,
            "product_name": product.name,
            "product_description": product.description,
            "brand_logo_text": product.branding.logo_text,
            "brand_primary_color": product.branding.primary_color,
            "brand_secondary_color": product.branding.secondary_color,
            "placeholder_features": [
                "AI newsletter writing assistant",
                "Subscriber engagement analytics",
                "Automated content curation",
                "A/B testing for subject lines",
                "Multi-platform distribution",
            ],
        }
    )
