"""
Admin Context Management.

This module provides session-based context tracking for admin users,
allowing them to switch between products and editions while maintaining
clear visibility of what they're currently editing.
"""

from typing import Optional, Tuple
from fastapi import Request

from app.products.config import Product, Edition
from app.products.registry import (
    ProductRegistry,
    EditionRegistry,
    get_active_edition,
)


# Session keys for admin context
ADMIN_PRODUCT_KEY = "admin_product_id"
ADMIN_EDITION_KEY = "admin_edition_version"

# Default product when none selected
DEFAULT_ADMIN_PRODUCT = "grounded"


def get_admin_context(request: Request) -> Tuple[Optional[Product], Optional[Edition]]:
    """
    Get the current admin context (product and edition) from the session.

    Args:
        request: FastAPI request object

    Returns:
        Tuple of (Product, Edition) or (None, None) if not set

    Note:
        Always defaults to the ACTIVE edition unless a specific edition
        cookie is set. This prevents accidentally landing on old editions.
    """
    # Try to get from session
    session = getattr(request.state, "session", {}) if hasattr(request, "state") else {}

    # Also check cookies as fallback
    product_id = session.get(ADMIN_PRODUCT_KEY)
    edition_version = session.get(ADMIN_EDITION_KEY)

    # If not in session, check cookies
    if not product_id:
        product_id = request.cookies.get(ADMIN_PRODUCT_KEY, DEFAULT_ADMIN_PRODUCT)

    if not edition_version:
        edition_version = request.cookies.get(ADMIN_EDITION_KEY)

    # Get product
    product = ProductRegistry.get(product_id) if product_id else None

    # Get edition - ALWAYS prefer active edition unless cookie explicitly set
    edition = None
    if product:
        active_edition = EditionRegistry.get_active(product.id)

        if edition_version:
            # Only use the cookie version if it matches a valid edition
            edition = EditionRegistry.get(product.id, edition_version)
            # If cookie has an old/invalid edition, use active instead
            if not edition:
                edition = active_edition
        else:
            # No cookie set - use active edition
            edition = active_edition

    return product, edition


def get_admin_context_dict(request: Request) -> dict:
    """
    Get admin context as a dictionary for template rendering.

    Returns a dict with all context information needed for admin templates.
    """
    product, edition = get_admin_context(request)

    # Get all products and their editions for the context switcher
    all_products = ProductRegistry.list_all()
    products_with_editions = []

    for p in all_products:
        editions = EditionRegistry.list_for_product(p.id)
        active_edition = EditionRegistry.get_active(p.id)

        products_with_editions.append({
            "product": p,
            "editions": editions,
            "active_edition": active_edition,
            "is_current": product and p.id == product.id,
        })

    return {
        # Current context
        "admin_product": product,
        "admin_edition": edition,
        "admin_product_id": product.id if product else None,
        "admin_product_name": product.name if product else "No Product Selected",
        "admin_edition_version": edition.version if edition else None,
        "admin_edition_name": edition.display_name if edition else None,
        "admin_edition_sealed": edition.is_sealed if edition else False,

        # Context indicator text
        "admin_context_label": _build_context_label(product, edition),
        "admin_context_class": _get_context_class(edition),

        # All products for switcher
        "admin_products": products_with_editions,
    }


def _build_context_label(product: Optional[Product], edition: Optional[Edition]) -> str:
    """Build the context label for display."""
    if not product:
        return "No Product Selected"

    label = product.name

    if edition:
        label += f" ({edition.version.upper()})"

    return label


def _get_context_class(edition: Optional[Edition]) -> str:
    """Get CSS class for context indicator based on edition state."""
    if not edition:
        return "bg-gray-500"
    if edition.is_active:
        return "bg-green-500"
    return "bg-blue-500"


def set_admin_context_cookies(
    response,
    product_id: str,
    edition_version: Optional[str] = None
) -> None:
    """
    Set admin context in response cookies.

    Args:
        response: FastAPI response object
        product_id: Product ID to set
        edition_version: Optional edition version to set
    """
    response.set_cookie(
        key=ADMIN_PRODUCT_KEY,
        value=product_id,
        max_age=60 * 60 * 24 * 30,  # 30 days
        httponly=True,
        samesite="lax"
    )

    if edition_version:
        response.set_cookie(
            key=ADMIN_EDITION_KEY,
            value=edition_version,
            max_age=60 * 60 * 24 * 30,  # 30 days
            httponly=True,
            samesite="lax"
        )
    else:
        # Clear edition cookie if not specified
        response.delete_cookie(key=ADMIN_EDITION_KEY)


def validate_admin_context(product_id: str, edition_version: Optional[str] = None) -> Tuple[bool, str]:
    """
    Validate that the requested admin context is valid.

    Args:
        product_id: Product ID to validate
        edition_version: Optional edition version to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    product = ProductRegistry.get(product_id)
    if not product:
        return False, f"Product '{product_id}' not found"

    if edition_version:
        edition = EditionRegistry.get(product_id, edition_version)
        if not edition:
            return False, f"Edition '{edition_version}' not found for product '{product_id}'"

    return True, ""
