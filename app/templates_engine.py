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

from app.products.config import Product, Edition, FeatureFlags, NavigationItem
from app.products.context import (
    get_current_product,
    get_current_edition,
    get_feature_flags,
)


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
                "feature_rag": features.rag_enabled,
                "feature_discovery": features.discovery_enabled,
                "feature_clusters": features.clusters_enabled,
                "feature_strategy": features.strategy_enabled,
                "feature_foundations": features.foundations_enabled,
                "feature_playbooks": features.playbooks_enabled,
                "feature_recommendations": features.recommendations_enabled,
                "feature_reviews": features.reviews_enabled,
                "feature_browse": features.browse_enabled,
                "feature_sources": features.sources_enabled,
                "feature_admin": features.admin_dashboard,
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
            "/toolkit": features.rag_enabled,
            "/browse": features.browse_enabled,
            "/clusters": features.clusters_enabled,
            "/strategy": features.strategy_enabled,
            "/foundations": features.foundations_enabled,
            "/sources": features.sources_enabled,
            "/admin": features.admin_dashboard,
            # Playbooks and recommendations are typically part of tools
        }

        # Check if route matches a feature-gated path
        for route_prefix, enabled in route_to_feature.items():
            if nav.route.startswith(route_prefix) and not enabled:
                return False

        return True


# Singleton instance for use across the application
templates = ProductAwareTemplates(directory="app/templates")


def get_templates() -> ProductAwareTemplates:
    """Get the product-aware templates instance."""
    return templates
