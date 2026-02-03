"""
Grounded Product Definition.

This is the primary product in the system. It defines:
- Grounded product configuration
- Grounded V1 (sealed, historical edition)
- Grounded V2 (sealed, historical edition)
- Grounded V3 (current, active edition) - AWS Lightsail deployment
"""

from datetime import datetime
from app.products.config import (
    Product,
    Edition,
    FeatureFlags,
    Branding,
    NavigationItem,
    ContentScope,
)
from app.products.registry import ProductRegistry, EditionRegistry


# =============================================================================
# PRODUCT DEFINITION
# =============================================================================

GROUNDED_PRODUCT = Product(
    id="grounded",
    name="Grounded",
    description="Grounded - Discover and master AI tools",
    branding=Branding(
        logo_text="Grounded",
        logo_path=None,  # Uses text-based logo
        primary_color="#3B82F6",    # Blue
        secondary_color="#1E40AF",  # Dark blue
        accent_color="#10B981",     # Green
    ),
    navigation=[
        NavigationItem(
            label="Tools",
            route="/tools",
            icon="wrench",
            requires_auth=False,
        ),
        NavigationItem(
            label="For You",
            route="/for-you",
            icon="star",
            requires_auth=False,
        ),
        NavigationItem(
            label="Matcher",
            route="/tools/finder",
            icon="search",
            requires_auth=False,
        ),
        NavigationItem(
            label="CDI",
            route="/tools/cdi",
            icon="chart",
            requires_auth=False,
        ),
        NavigationItem(
            label="Clusters",
            route="/clusters",
            icon="grid",
            requires_auth=False,
        ),
        NavigationItem(
            label="Sources",
            route="/sources",
            icon="link",
            requires_auth=False,
        ),
        NavigationItem(
            label="Foundations",
            route="/foundations",
            icon="book",
            requires_auth=False,
        ),
        NavigationItem(
            label="Activity",
            route="/toolkit",
            icon="clock",
            requires_auth=True,  # Activity requires login
        ),
        NavigationItem(
            label="Strategy",
            route="/strategy",
            icon="target",
            requires_auth=False,
        ),
    ],
    content_scope=ContentScope.TOOLS,
    is_active=True,
)


# =============================================================================
# EDITION DEFINITIONS
# =============================================================================

# -----------------------------------------------------------------------------
# TOOLKIT V1 - Sealed Historical Edition
# -----------------------------------------------------------------------------
# This edition represents the state of the toolkit at a specific point in time.
# It is sealed and serves as a historical reference. The git reference points
# to the commit where V1 was finalized.
#
# IMPORTANT: V1 is SEALED. Do not add new features to this edition.
# Any new features should only be added to V2 or later editions.

GROUNDED_V1_FEATURES = FeatureFlags(
    # =========================================================================
    # CORE FEATURES - V1 had basic RAG, no discovery
    # =========================================================================
    rag_enabled=True,
    discovery_enabled=False,  # Discovery pipeline was not in V1

    # =========================================================================
    # TOOL FEATURES - V1 had basic tool browsing
    # =========================================================================
    clusters_enabled=True,
    tool_finder_enabled=False,  # Tool finder wizard was not in V1
    cdi_scores_enabled=True,    # CDI scores were in V1
    advanced_search_enabled=False,  # Advanced search was not in V1

    # =========================================================================
    # LEARNING CONTENT - V1 had foundations, no playbooks
    # =========================================================================
    foundations_enabled=True,
    playbooks_enabled=False,  # Playbooks were not in V1

    # =========================================================================
    # PERSONALIZATION - V1 had no personalization features
    # =========================================================================
    strategy_enabled=False,       # Strategy builder was not in V1
    recommendations_enabled=False,  # Recommendations were not in V1
    reviews_enabled=False,        # Reviews were not in V1
    review_voting_enabled=False,  # Review voting was not in V1
    activity_history_enabled=False,  # Activity history was not in V1

    # =========================================================================
    # CONTENT ACCESS - V1 had browse and sources
    # =========================================================================
    browse_enabled=True,
    sources_enabled=True,

    # =========================================================================
    # ADMINISTRATION - V1 had basic admin only
    # =========================================================================
    admin_dashboard_enabled=True,
    admin_ingestion_enabled=True,
    admin_users_enabled=True,
    admin_analytics_enabled=False,  # Analytics were not in V1
    admin_feedback_enabled=False,   # Feedback management was not in V1
    admin_playbooks_enabled=False,  # Playbook management was not in V1
    admin_discovery_enabled=False,  # Discovery management was not in V1
)

GROUNDED_V1_EDITION = Edition(
    product_id="grounded",
    version="v1",
    display_name="Grounded V1",
    feature_flags=GROUNDED_V1_FEATURES,
    is_sealed=True,
    is_active=False,
    sealed_at=datetime(2025, 1, 15, 0, 0, 0),  # Approximate seal date
    sealed_reason="V1 finalized before V2 development began",
    git_reference="a794966e77bcf1ef16ee3d93ed2a3fc5779b74a6",
    created_at=datetime(2024, 12, 1, 0, 0, 0),  # Approximate creation date
    description=(
        "Initial version of Grounded with core RAG functionality, "
        "cluster organization, foundations, and document browsing. "
        "This version predates the discovery pipeline, strategy builder, "
        "personalized recommendations, and user reviews."
    ),
)


# -----------------------------------------------------------------------------
# TOOLKIT V2 - Sealed Historical Edition
# -----------------------------------------------------------------------------
# V2 represented full feature set before Lightsail migration.
# It is now sealed and serves as a historical reference.
#
# IMPORTANT: V2 is SEALED. Do not add new features to this edition.
# Any new features should only be added to V3 or later editions.

GROUNDED_V2_FEATURES = FeatureFlags(
    # =========================================================================
    # CORE FEATURES - All enabled
    # =========================================================================
    rag_enabled=True,
    discovery_enabled=True,

    # =========================================================================
    # TOOL FEATURES - All enabled
    # =========================================================================
    clusters_enabled=True,
    tool_finder_enabled=True,
    cdi_scores_enabled=True,
    advanced_search_enabled=True,

    # =========================================================================
    # LEARNING CONTENT - All enabled
    # =========================================================================
    foundations_enabled=True,
    playbooks_enabled=True,

    # =========================================================================
    # PERSONALIZATION - All enabled
    # =========================================================================
    strategy_enabled=True,
    recommendations_enabled=True,
    reviews_enabled=True,
    review_voting_enabled=True,
    activity_history_enabled=True,

    # =========================================================================
    # CONTENT ACCESS - All enabled
    # =========================================================================
    browse_enabled=True,
    sources_enabled=True,

    # =========================================================================
    # ADMINISTRATION - All enabled
    # =========================================================================
    admin_dashboard_enabled=True,
    admin_ingestion_enabled=True,
    admin_users_enabled=True,
    admin_analytics_enabled=True,
    admin_feedback_enabled=True,
    admin_playbooks_enabled=True,
    admin_discovery_enabled=True,
)

GROUNDED_V2_EDITION = Edition(
    product_id="grounded",
    version="v2",
    display_name="Grounded V2",
    feature_flags=GROUNDED_V2_FEATURES,
    is_sealed=True,
    is_active=False,
    sealed_at=datetime(2026, 2, 3, 0, 0, 0),
    sealed_reason="V2 finalized before V3 Lightsail deployment",
    git_reference="9cdb9e8261a9061e07e927db6a745a8967f7edf4",
    created_at=datetime(2025, 1, 1, 0, 0, 0),
    description=(
        "Full feature set version of Grounded including "
        "discovery pipeline, strategy builder, playbooks, recommendations, "
        "and user reviews. Sealed before AWS Lightsail migration."
    ),
)


# -----------------------------------------------------------------------------
# TOOLKIT V3 - Current Active Edition (AWS Lightsail)
# -----------------------------------------------------------------------------
# This is the current working version deployed on AWS Lightsail.
# It is not sealed and continues to receive updates.
#
# Lightsail Instance: GROUNDED
# Region: eu-west-2 (London, Zone A)
# Public IPv4: 3.10.224.68
# Public IPv6: 2a05:d01c:39:4900:1f55:672a:3ac7:c465

GROUNDED_V3_FEATURES = FeatureFlags(
    # =========================================================================
    # CORE FEATURES - All enabled
    # =========================================================================
    rag_enabled=True,
    discovery_enabled=True,

    # =========================================================================
    # TOOL FEATURES - All enabled
    # =========================================================================
    clusters_enabled=True,
    tool_finder_enabled=True,
    cdi_scores_enabled=True,
    advanced_search_enabled=True,

    # =========================================================================
    # LEARNING CONTENT - All enabled
    # =========================================================================
    foundations_enabled=True,
    playbooks_enabled=True,

    # =========================================================================
    # PERSONALIZATION - All enabled
    # =========================================================================
    strategy_enabled=True,
    recommendations_enabled=True,
    reviews_enabled=True,
    review_voting_enabled=True,
    activity_history_enabled=True,

    # =========================================================================
    # CONTENT ACCESS - All enabled
    # =========================================================================
    browse_enabled=True,
    sources_enabled=True,

    # =========================================================================
    # ADMINISTRATION - All enabled
    # =========================================================================
    admin_dashboard_enabled=True,
    admin_ingestion_enabled=True,
    admin_users_enabled=True,
    admin_analytics_enabled=True,
    admin_feedback_enabled=True,
    admin_playbooks_enabled=True,
    admin_discovery_enabled=True,
)

GROUNDED_V3_EDITION = Edition(
    product_id="grounded",
    version="v3",
    display_name="Grounded V3",
    feature_flags=GROUNDED_V3_FEATURES,
    is_sealed=False,
    is_active=True,
    sealed_at=None,
    sealed_reason=None,
    git_reference=None,  # Not sealed, no fixed reference
    created_at=datetime(2026, 2, 3, 0, 0, 0),
    description=(
        "Current version of Grounded deployed on AWS Lightsail (London). "
        "Full feature set with production infrastructure including "
        "discovery pipeline, strategy builder, playbooks, recommendations, "
        "and user reviews."
    ),
)


# =============================================================================
# REGISTRATION
# =============================================================================

def register_grounded() -> None:
    """
    Register the Grounded product and its editions.

    This function should be called during application startup.
    """
    # Register the product first
    ProductRegistry.register(GROUNDED_PRODUCT)

    # Register editions (V1, V2 sealed, then V3 active)
    EditionRegistry.register(GROUNDED_V1_EDITION)
    EditionRegistry.register(GROUNDED_V2_EDITION)
    EditionRegistry.register(GROUNDED_V3_EDITION)
