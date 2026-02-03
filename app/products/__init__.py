"""
Products, Editions, and Version Sealing Architecture.

This module provides the foundational architecture for managing:
- Products: Distinct apps sharing infrastructure (Grounded, AI Audio, Letter+)
- Editions: Different versions of the same product (Grounded V1, V2, etc.)
- Sealing: Mechanism to freeze versions so new versions don't affect sealed ones

Usage:
    from app.products import get_product, get_edition, get_active_edition
    from app.products import ProductRegistry, EditionRegistry

    # Get the current active product and edition
    grounded = get_product("grounded")
    current_edition = get_active_edition("grounded")

    # Check if an edition is sealed
    v1 = get_edition("grounded", "v1")
    if v1.is_sealed:
        print("V1 is frozen - no new features")
"""

from app.products.config import (
    Product,
    Edition,
    FeatureFlags,
    Branding,
    NavigationItem,
    ContentScope,
)
from app.products.registry import (
    ProductRegistry,
    EditionRegistry,
    get_product,
    get_edition,
    get_active_edition,
    list_products,
    list_editions,
    create_new_edition,
)
from app.products.context import (
    get_current_product,
    get_current_edition,
    get_feature_flags,
    is_feature_enabled,
    product_context,
)
from app.products.guards import (
    FeatureDisabledError,
    check_feature,
    require_feature,
    require_features,
    require_any_feature,
    get_feature_disabled_context,
    # Convenience dependencies
    require_rag,
    require_reviews,
    require_strategy,
    require_recommendations,
    require_tool_finder,
    require_advanced_search,
    require_browse,
    require_sources,
    require_clusters,
    require_foundations,
    require_playbooks,
    require_activity_history,
    # Admin feature guards
    require_admin_dashboard,
    require_admin_ingestion,
    require_admin_users,
    require_admin_analytics,
    require_admin_feedback,
    require_admin_playbooks,
    require_admin_discovery,
)

__all__ = [
    # Models
    "Product",
    "Edition",
    "FeatureFlags",
    "Branding",
    "NavigationItem",
    "ContentScope",
    # Registry
    "ProductRegistry",
    "EditionRegistry",
    # Registry helper functions
    "get_product",
    "get_edition",
    "get_active_edition",
    "list_products",
    "list_editions",
    "create_new_edition",
    # Context helpers
    "get_current_product",
    "get_current_edition",
    "get_feature_flags",
    "is_feature_enabled",
    "product_context",
    # Feature guards
    "FeatureDisabledError",
    "check_feature",
    "require_feature",
    "require_features",
    "require_any_feature",
    "get_feature_disabled_context",
    # Convenience dependencies
    "require_rag",
    "require_reviews",
    "require_strategy",
    "require_recommendations",
    "require_tool_finder",
    "require_advanced_search",
    "require_browse",
    "require_sources",
    "require_clusters",
    "require_foundations",
    "require_playbooks",
    "require_activity_history",
    # Admin feature guards
    "require_admin_dashboard",
    "require_admin_ingestion",
    "require_admin_users",
    "require_admin_analytics",
    "require_admin_feedback",
    "require_admin_playbooks",
    "require_admin_discovery",
]
