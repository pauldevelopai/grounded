"""
Product Context Utilities.

This module provides utilities for accessing the current product and edition
context throughout the application. It includes FastAPI dependencies and
helper functions for feature flag checking.
"""

from typing import Optional, Any
from fastapi import Request

from app.products.config import Product, Edition, FeatureFlags
from app.products.registry import (
    ProductRegistry,
    EditionRegistry,
    get_active_edition,
)


# Default product when none is specified
DEFAULT_PRODUCT_ID = "grounded"


def _get_user_from_request(request: Optional[Request]) -> Optional[Any]:
    """Try to get user from request state (set by auth middleware)."""
    if request is None:
        return None
    try:
        return getattr(request.state, "user", None)
    except Exception:
        return None


def get_current_product(request: Optional[Request] = None) -> Product:
    """
    Get the current product based on user preference or default.

    Priority:
    1. User's selected_product preference (if logged in)
    2. Default product (grounded)

    Args:
        request: Optional FastAPI request object

    Returns:
        Current Product instance
    """
    product_id = DEFAULT_PRODUCT_ID

    # Try to get user's preference
    user = _get_user_from_request(request)
    if user and hasattr(user, "selected_product") and user.selected_product:
        product_id = user.selected_product

    product = ProductRegistry.get(product_id)
    if product is None:
        # Fall back to default if user's selected product doesn't exist
        product = ProductRegistry.get(DEFAULT_PRODUCT_ID)

    if product is None:
        raise RuntimeError(
            f"Default product '{DEFAULT_PRODUCT_ID}' not registered. "
            "Ensure register_all_products() is called during startup."
        )
    return product


def get_current_edition(request: Optional[Request] = None) -> Edition:
    """
    Get the current edition based on user preference or active edition.

    Priority:
    1. User's selected_edition preference (if logged in and valid)
    2. Active edition for the product

    Args:
        request: Optional FastAPI request object

    Returns:
        Current Edition instance
    """
    product = get_current_product(request)

    # Try to get user's edition preference
    user = _get_user_from_request(request)
    if user and hasattr(user, "selected_edition") and user.selected_edition:
        edition = EditionRegistry.get(product.id, user.selected_edition)
        if edition:
            return edition

    # Fall back to active edition
    edition = get_active_edition(product.id)
    if edition is None:
        raise RuntimeError(
            f"No active edition for product '{product.id}'. "
            "Ensure editions are registered during startup."
        )
    return edition


def get_feature_flags(request: Optional[Request] = None) -> FeatureFlags:
    """
    Get the feature flags for the current edition.

    Args:
        request: Optional FastAPI request object

    Returns:
        FeatureFlags instance for current edition
    """
    edition = get_current_edition(request)
    return edition.feature_flags


def is_feature_enabled(feature_name: str, request: Optional[Request] = None) -> bool:
    """
    Check if a specific feature is enabled in the current edition.

    Args:
        feature_name: Name of the feature flag (e.g., "rag", "reviews")
                     Can omit the "_enabled" suffix.
        request: Optional FastAPI request object

    Returns:
        True if feature is enabled, False otherwise

    Raises:
        AttributeError: If feature_name is not a valid feature flag
    """
    flags = get_feature_flags(request)
    return flags.is_enabled(feature_name)


# FastAPI dependency for injecting product context
async def product_context(request: Request) -> dict:
    """
    FastAPI dependency that provides product context to templates.

    This can be used in route handlers to get product information:

        @router.get("/")
        async def home(ctx: dict = Depends(product_context)):
            return templates.TemplateResponse("home.html", {
                "request": request,
                "product": ctx["product"],
                "edition": ctx["edition"],
                "features": ctx["features"],
            })

    Returns:
        Dict with product, edition, and feature flags
    """
    product = get_current_product(request)
    edition = get_current_edition(request)

    return {
        "product": product,
        "edition": edition,
        "features": edition.feature_flags,
        "product_name": product.name,
        "edition_name": edition.display_name,
        "is_sealed": edition.is_sealed,
    }
