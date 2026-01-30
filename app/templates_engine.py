"""
Centralized Template Rendering Engine.

This module provides a custom Jinja2Templates class that automatically
injects product and edition context into all template responses. This
ensures the UI is driven entirely by the selected Product + Edition.
"""

from typing import Any, Optional
from fastapi import Request
from fastapi.templating import Jinja2Templates
from starlette.responses import Response
from markupsafe import Markup
import markdown

from app.products.config import Product, Edition, FeatureFlags, NavigationItem
from app.products.context import (
    get_current_product,
    get_current_edition,
    get_feature_flags,
)


def markdown_filter(text: str) -> Markup:
    """Convert markdown text to HTML."""
    if not text:
        return Markup("")
    html = markdown.markdown(
        text,
        extensions=['fenced_code', 'tables', 'nl2br']
    )
    return Markup(html)


class ProductAwareTemplates(Jinja2Templates):
    """
    Custom Jinja2Templates that automatically injects product context.

    All template responses will include:
    - product: Current Product instance
    - edition: Current Edition instance
    - features: FeatureFlags for current edition
    - product_name: Display name of the product
    - edition_label: Version label (e.g., "V1", "V2")
    - branding: Product branding config
    - navigation: Product navigation items
    """

    def TemplateResponse(
        self,
        name: str,
        context: dict,
        status_code: int = 200,
        headers: Optional[dict] = None,
        media_type: Optional[str] = None,
        background: Optional[Any] = None,
    ) -> Response:
        """
        Override TemplateResponse to inject product context.

        The 'request' key must be present in context (FastAPI requirement).
        Product context is automatically added before rendering.
        """
        request = context.get("request")
        if request:
            # Inject product context
            context = self._inject_product_context(context, request)

        return super().TemplateResponse(
            name=name,
            context=context,
            status_code=status_code,
            headers=headers,
            media_type=media_type,
            background=background,
        )

    def _inject_product_context(self, context: dict, request: Request) -> dict:
        """
        Inject product and edition context into template context.

        This ensures all templates have access to:
        - Product identity (name, branding, navigation)
        - Edition info (version label, sealed status)
        - Feature flags
        """
        try:
            product = get_current_product(request)
            edition = get_current_edition(request)
            features = edition.feature_flags

            # Build navigation items for template
            nav_items = self._build_navigation(product, edition, context.get("user"))

            # Product context
            context.update({
                # Core objects
                "product": product,
                "edition": edition,
                "features": features,

                # Convenience accessors for templates
                "product_id": product.id,
                "product_name": product.name,
                "product_description": product.description,
                "product_active": product.is_active,

                # Branding
                "branding": product.branding,
                "brand_logo_text": product.branding.logo_text,
                "brand_primary_color": product.branding.primary_color,
                "brand_secondary_color": product.branding.secondary_color,
                "brand_accent_color": product.branding.accent_color,

                # Edition info
                "edition_version": edition.version,
                "edition_label": edition.version.upper(),
                "edition_name": edition.display_name,
                "edition_sealed": edition.is_sealed,
                "edition_active": edition.is_active,

                # Navigation (filtered by auth and features)
                "nav_items": nav_items,

                # Feature flags as booleans for easy template access
                # Core
                "feature_rag": features.rag_enabled,
                "feature_discovery": features.discovery_enabled,
                # Tools
                "feature_clusters": features.clusters_enabled,
                "feature_tool_finder": features.tool_finder_enabled,
                "feature_cdi_scores": features.cdi_scores_enabled,
                "feature_advanced_search": features.advanced_search_enabled,
                # Learning
                "feature_foundations": features.foundations_enabled,
                "feature_playbooks": features.playbooks_enabled,
                # Personalization
                "feature_strategy": features.strategy_enabled,
                "feature_recommendations": features.recommendations_enabled,
                "feature_reviews": features.reviews_enabled,
                "feature_review_voting": features.review_voting_enabled,
                "feature_activity_history": features.activity_history_enabled,
                # Content
                "feature_browse": features.browse_enabled,
                "feature_sources": features.sources_enabled,
                # Admin
                "feature_admin": features.admin_dashboard_enabled,
                "feature_admin_ingestion": features.admin_ingestion_enabled,
                "feature_admin_users": features.admin_users_enabled,
                "feature_admin_analytics": features.admin_analytics_enabled,
                "feature_admin_feedback": features.admin_feedback_enabled,
                "feature_admin_playbooks": features.admin_playbooks_enabled,
                "feature_admin_discovery": features.admin_discovery_enabled,
            })

        except Exception:
            # If product system not initialized, provide empty defaults
            # This allows the app to start even if products aren't registered
            context.setdefault("product_name", "Application")
            context.setdefault("brand_logo_text", "App")
            context.setdefault("nav_items", [])
            context.setdefault("edition_label", "")
            context.setdefault("edition_sealed", False)

        return context

    def _build_navigation(
        self,
        product: Product,
        edition: Edition,
        user: Optional[Any]
    ) -> list[dict]:
        """
        Build navigation items filtered by auth status and feature flags.

        Returns a list of dicts suitable for template rendering:
        [{"label": "Tools", "route": "/tools", "icon": "wrench", "active": False}, ...]
        """
        features = edition.feature_flags
        nav_items = []

        for nav in product.navigation:
            # Skip if requires auth and user not logged in
            if nav.requires_auth and not user:
                continue

            # Skip if requires admin and user is not admin
            if nav.requires_admin and (not user or not getattr(user, "is_admin", False)):
                continue

            # Skip based on feature flags (map route to feature)
            if not self._is_nav_enabled(nav, features):
                continue

            nav_items.append({
                "label": nav.label,
                "route": nav.route,
                "icon": nav.icon,
            })

        return nav_items

    def _is_nav_enabled(self, nav: NavigationItem, features: FeatureFlags) -> bool:
        """
        Check if a navigation item is enabled based on feature flags.

        Maps routes to their corresponding feature flags.
        """
        route_to_feature = {
            # Core features
            "/toolkit": features.rag_enabled,
            "/toolkit/history": features.activity_history_enabled,
            # Tool features
            "/tools/finder": features.tool_finder_enabled,
            "/tools/cdi": features.cdi_scores_enabled,
            "/clusters": features.clusters_enabled,
            # Learning content
            "/foundations": features.foundations_enabled,
            # Personalization
            "/for-you": features.recommendations_enabled,
            "/strategy": features.strategy_enabled,
            # Content
            "/browse": features.browse_enabled,
            "/sources": features.sources_enabled,
            # Admin
            "/admin": features.admin_dashboard_enabled,
        }

        # Check if route matches a feature-gated path (most specific first)
        # Sort by length descending to match more specific routes first
        for route_prefix in sorted(route_to_feature.keys(), key=len, reverse=True):
            if nav.route.startswith(route_prefix):
                if not route_to_feature[route_prefix]:
                    return False
                # Found a matching prefix that is enabled, allow it
                break

        return True


# Singleton instance for use across the application
templates = ProductAwareTemplates(directory="app/templates")

# Register custom filters
templates.env.filters["markdown"] = markdown_filter


def get_templates() -> ProductAwareTemplates:
    """Get the product-aware templates instance."""
    return templates
