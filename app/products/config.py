"""
Product and Edition Configuration Models.

This module defines the core data structures for products, editions,
and their associated configuration including branding, navigation,
and feature flags.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from enum import Enum


def utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class ContentScope(Enum):
    """Defines the default content scope for a product."""
    TOOLS = "tools"           # AI tools and productivity
    AUDIO = "audio"           # Audio production and editing
    WRITING = "writing"       # Writing and letter composition
    GENERAL = "general"       # General purpose


@dataclass(frozen=True)
class Branding:
    """
    Product branding configuration.

    Attributes:
        logo_text: Text displayed as logo (e.g., "Grounded")
        logo_path: Optional path to logo image asset
        primary_color: Primary brand color (hex)
        secondary_color: Secondary brand color (hex)
        accent_color: Accent color for highlights (hex)
    """
    logo_text: str
    logo_path: Optional[str] = None
    primary_color: str = "#3B82F6"   # Blue
    secondary_color: str = "#1E40AF"  # Dark blue
    accent_color: str = "#10B981"     # Green


@dataclass(frozen=True)
class NavigationItem:
    """
    A single navigation menu item.

    Attributes:
        label: Display text for the nav item
        route: URL path or route name
        icon: Optional icon name (for icon libraries)
        requires_auth: Whether this item requires authentication
        requires_admin: Whether this item requires admin privileges
    """
    label: str
    route: str
    icon: Optional[str] = None
    requires_auth: bool = False
    requires_admin: bool = False


@dataclass
class FeatureFlags:
    """
    Feature flags for controlling functionality in editions.

    Each flag controls a specific feature that can be enabled or disabled
    per edition. This allows different editions to have different capabilities.

    Feature flags are organized into categories:
    - Core: Fundamental platform features
    - Tools: Tool-related functionality
    - Learning: Educational content and materials
    - Personalization: User-specific features
    - Content: Content access and browsing
    - Administration: Admin-only features

    IMPORTANT: When adding new flags, also update:
    - clone() method
    - to_dict() method
    - is_enabled() method
    - Toolkit edition definitions if applicable
    """

    # ==========================================================================
    # CORE FEATURES
    # ==========================================================================
    # RAG (Retrieval Augmented Generation) chat functionality
    rag_enabled: bool = True
    # Tool discovery pipeline for finding new tools
    discovery_enabled: bool = True

    # ==========================================================================
    # TOOL FEATURES
    # ==========================================================================
    # Tool clustering and categorization
    clusters_enabled: bool = True
    # Tool finder / recommendation wizard
    tool_finder_enabled: bool = True
    # CDI (Cost/Difficulty/Invasiveness) scoring display
    cdi_scores_enabled: bool = True
    # Advanced tool filtering and search
    advanced_search_enabled: bool = True

    # ==========================================================================
    # LEARNING CONTENT
    # ==========================================================================
    # Learning foundations/materials
    foundations_enabled: bool = True
    # Tool playbooks/guides
    playbooks_enabled: bool = True

    # ==========================================================================
    # PERSONALIZATION
    # ==========================================================================
    # Strategy builder for implementation planning
    strategy_enabled: bool = True
    # Personalized tool recommendations
    recommendations_enabled: bool = True
    # User reviews and ratings system
    reviews_enabled: bool = True
    # Review voting (helpful/not helpful)
    review_voting_enabled: bool = True
    # Activity history tracking
    activity_history_enabled: bool = True

    # ==========================================================================
    # CONTENT ACCESS
    # ==========================================================================
    # Document browsing
    browse_enabled: bool = True
    # Citation sources
    sources_enabled: bool = True

    # ==========================================================================
    # ADMINISTRATION
    # ==========================================================================
    # Admin dashboard access
    admin_dashboard_enabled: bool = True
    # Admin document ingestion
    admin_ingestion_enabled: bool = True
    # Admin user management
    admin_users_enabled: bool = True
    # Admin analytics
    admin_analytics_enabled: bool = True
    # Admin feedback review
    admin_feedback_enabled: bool = True
    # Admin playbook management
    admin_playbooks_enabled: bool = True
    # Admin discovery management
    admin_discovery_enabled: bool = True

    def is_enabled(self, feature_name: str) -> bool:
        """
        Check if a feature is enabled by name.

        Args:
            feature_name: Name of the feature flag (e.g., "rag_enabled", "reviews")
                         Can omit the "_enabled" suffix.

        Returns:
            True if feature is enabled, False otherwise

        Raises:
            AttributeError: If feature_name is not a valid feature flag
        """
        # Normalize feature name - add _enabled suffix if not present
        if not feature_name.endswith("_enabled"):
            feature_name = f"{feature_name}_enabled"

        if not hasattr(self, feature_name):
            raise AttributeError(f"Unknown feature flag: {feature_name}")

        return getattr(self, feature_name)

    def clone(self, **overrides) -> "FeatureFlags":
        """Create a copy with optional overrides."""
        current = self.to_dict()
        current.update(overrides)
        return FeatureFlags(**current)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            # Core
            "rag_enabled": self.rag_enabled,
            "discovery_enabled": self.discovery_enabled,
            # Tools
            "clusters_enabled": self.clusters_enabled,
            "tool_finder_enabled": self.tool_finder_enabled,
            "cdi_scores_enabled": self.cdi_scores_enabled,
            "advanced_search_enabled": self.advanced_search_enabled,
            # Learning
            "foundations_enabled": self.foundations_enabled,
            "playbooks_enabled": self.playbooks_enabled,
            # Personalization
            "strategy_enabled": self.strategy_enabled,
            "recommendations_enabled": self.recommendations_enabled,
            "reviews_enabled": self.reviews_enabled,
            "review_voting_enabled": self.review_voting_enabled,
            "activity_history_enabled": self.activity_history_enabled,
            # Content
            "browse_enabled": self.browse_enabled,
            "sources_enabled": self.sources_enabled,
            # Administration
            "admin_dashboard_enabled": self.admin_dashboard_enabled,
            "admin_ingestion_enabled": self.admin_ingestion_enabled,
            "admin_users_enabled": self.admin_users_enabled,
            "admin_analytics_enabled": self.admin_analytics_enabled,
            "admin_feedback_enabled": self.admin_feedback_enabled,
            "admin_playbooks_enabled": self.admin_playbooks_enabled,
            "admin_discovery_enabled": self.admin_discovery_enabled,
        }

    @classmethod
    def all_disabled(cls) -> "FeatureFlags":
        """Create a FeatureFlags instance with all features disabled."""
        return cls(**{k: False for k in cls().to_dict().keys()})

    @classmethod
    def all_enabled(cls) -> "FeatureFlags":
        """Create a FeatureFlags instance with all features enabled."""
        return cls(**{k: True for k in cls().to_dict().keys()})


@dataclass
class Product:
    """
    A product definition.

    Products are distinct applications that share infrastructure but
    present as separate apps to users. Examples: Grounded, AI Audio, Letter+

    Attributes:
        id: Unique identifier (e.g., "grounded")
        name: Display name (e.g., "Grounded")
        description: Short product description
        branding: Branding configuration
        navigation: List of navigation items
        content_scope: Default content scope
        is_active: Whether this product is currently active/available
    """
    id: str
    name: str
    description: str
    branding: Branding
    navigation: list[NavigationItem] = field(default_factory=list)
    content_scope: ContentScope = ContentScope.GENERAL
    is_active: bool = True

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if isinstance(other, Product):
            return self.id == other.id
        return False


@dataclass
class Edition:
    """
    An edition/version of a product.

    Editions represent different versions of the same product. They share
    the product identity but can have different features and capabilities.

    Version Sealing:
    - When an edition is sealed, it becomes read-only
    - No new features are added to sealed editions
    - Sealed editions serve as historical references

    Attributes:
        product_id: ID of the parent product
        version: Version label (e.g., "v1", "v2")
        display_name: Human-readable name (e.g., "Toolkit V2")
        feature_flags: Features enabled in this edition
        is_sealed: Whether this edition is sealed (frozen)
        is_active: Whether this is the active/current edition
        sealed_at: Datetime when the edition was sealed
        sealed_reason: Reason for sealing (documentation)
        git_reference: Optional git commit/tag reference for sealed editions
        created_at: When this edition was defined
        description: Optional description of this edition
    """
    product_id: str
    version: str
    display_name: str
    feature_flags: FeatureFlags
    is_sealed: bool = False
    is_active: bool = True
    sealed_at: Optional[datetime] = None
    sealed_reason: Optional[str] = None
    git_reference: Optional[str] = None
    created_at: datetime = field(default_factory=utc_now)
    description: Optional[str] = None

    @property
    def edition_id(self) -> str:
        """Unique identifier combining product and version."""
        return f"{self.product_id}:{self.version}"

    def __hash__(self):
        return hash(self.edition_id)

    def __eq__(self, other):
        if isinstance(other, Edition):
            return self.edition_id == other.edition_id
        return False

    def seal(self, reason: Optional[str] = None) -> "Edition":
        """
        Seal this edition, making it read-only.

        Args:
            reason: Optional reason for sealing

        Returns:
            Self for chaining

        Raises:
            ValueError: If already sealed
        """
        if self.is_sealed:
            raise ValueError(f"Edition {self.edition_id} is already sealed")

        self.is_sealed = True
        self.is_active = False
        self.sealed_at = utc_now()
        self.sealed_reason = reason
        return self

    def clone_for_new_version(
        self,
        new_version: str,
        display_name: Optional[str] = None,
        feature_overrides: Optional[dict] = None,
    ) -> "Edition":
        """
        Create a new edition based on this one.

        This is the primary mechanism for creating new versions:
        1. Clone an existing edition's configuration
        2. Assign a new version label
        3. Optionally override feature flags

        Args:
            new_version: Version label for new edition (e.g., "v3")
            display_name: Optional custom display name
            feature_overrides: Optional dict of feature flag overrides

        Returns:
            New Edition instance (not yet registered)
        """
        new_flags = self.feature_flags.clone(**(feature_overrides or {}))

        return Edition(
            product_id=self.product_id,
            version=new_version,
            display_name=display_name or f"{self.product_id.replace('_', ' ').title()} {new_version.upper()}",
            feature_flags=new_flags,
            is_sealed=False,
            is_active=True,
            description=f"Cloned from {self.edition_id}",
        )
