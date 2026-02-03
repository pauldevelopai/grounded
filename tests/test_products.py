"""
Tests for Products, Editions, and Version Sealing.

These tests verify:
- Product registration and lookup
- Edition registration and lookup
- Feature flags functionality
- Version sealing behavior
- Creating new editions from existing ones
"""

import pytest
from datetime import datetime

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
)


@pytest.fixture(autouse=True)
def clear_registries():
    """Clear registries before and after each test."""
    ProductRegistry.clear()
    EditionRegistry.clear()
    yield
    ProductRegistry.clear()
    EditionRegistry.clear()


@pytest.fixture
def sample_product():
    """Create a sample product for testing."""
    return Product(
        id="test_product",
        name="Test Product",
        description="A test product",
        branding=Branding(logo_text="Test"),
        navigation=[
            NavigationItem(label="Home", route="/"),
            NavigationItem(label="Dashboard", route="/dashboard", requires_auth=True),
        ],
        content_scope=ContentScope.GENERAL,
    )


@pytest.fixture
def sample_edition(sample_product):
    """Create a sample edition for testing."""
    ProductRegistry.register(sample_product)
    return Edition(
        product_id="test_product",
        version="v1",
        display_name="Test V1",
        feature_flags=FeatureFlags(
            rag_enabled=True,
            discovery_enabled=False,
        ),
    )


class TestProduct:
    """Tests for Product model."""

    def test_product_creation(self, sample_product):
        """Test basic product creation."""
        assert sample_product.id == "test_product"
        assert sample_product.name == "Test Product"
        assert sample_product.is_active is True
        assert sample_product.content_scope == ContentScope.GENERAL

    def test_product_branding(self, sample_product):
        """Test product branding configuration."""
        assert sample_product.branding.logo_text == "Test"
        assert sample_product.branding.primary_color == "#3B82F6"

    def test_product_navigation(self, sample_product):
        """Test product navigation items."""
        assert len(sample_product.navigation) == 2
        assert sample_product.navigation[0].label == "Home"
        assert sample_product.navigation[1].requires_auth is True


class TestEdition:
    """Tests for Edition model."""

    def test_edition_creation(self, sample_edition):
        """Test basic edition creation."""
        assert sample_edition.product_id == "test_product"
        assert sample_edition.version == "v1"
        assert sample_edition.edition_id == "test_product:v1"
        assert sample_edition.is_sealed is False
        assert sample_edition.is_active is True

    def test_edition_seal(self, sample_edition):
        """Test sealing an edition."""
        sample_edition.seal(reason="Test sealing")

        assert sample_edition.is_sealed is True
        assert sample_edition.is_active is False
        assert sample_edition.sealed_at is not None
        assert sample_edition.sealed_reason == "Test sealing"

    def test_edition_seal_twice_raises(self, sample_edition):
        """Test that sealing twice raises an error."""
        sample_edition.seal()

        with pytest.raises(ValueError, match="already sealed"):
            sample_edition.seal()

    def test_edition_clone(self, sample_edition):
        """Test cloning an edition for a new version."""
        new_edition = sample_edition.clone_for_new_version(
            new_version="v2",
            display_name="Test V2",
            feature_overrides={"discovery_enabled": True},
        )

        assert new_edition.version == "v2"
        assert new_edition.display_name == "Test V2"
        assert new_edition.feature_flags.rag_enabled is True  # Inherited
        assert new_edition.feature_flags.discovery_enabled is True  # Overridden
        assert new_edition.is_sealed is False
        assert new_edition.is_active is True


class TestFeatureFlags:
    """Tests for FeatureFlags."""

    def test_default_flags(self):
        """Test default feature flag values."""
        flags = FeatureFlags()
        assert flags.rag_enabled is True
        assert flags.discovery_enabled is True
        assert flags.admin_dashboard_enabled is True

    def test_custom_flags(self):
        """Test custom feature flag values."""
        flags = FeatureFlags(
            rag_enabled=False,
            discovery_enabled=True,
        )
        assert flags.rag_enabled is False
        assert flags.discovery_enabled is True

    def test_flags_clone(self):
        """Test cloning flags with overrides."""
        original = FeatureFlags(rag_enabled=True, discovery_enabled=False)
        cloned = original.clone(discovery_enabled=True)

        assert original.discovery_enabled is False
        assert cloned.discovery_enabled is True
        assert cloned.rag_enabled is True

    def test_flags_to_dict(self):
        """Test converting flags to dictionary."""
        flags = FeatureFlags(rag_enabled=True, discovery_enabled=False)
        d = flags.to_dict()

        assert d["rag_enabled"] is True
        assert d["discovery_enabled"] is False
        assert "admin_dashboard_enabled" in d

    def test_is_enabled_method(self):
        """Test the is_enabled method with various inputs."""
        flags = FeatureFlags(reviews_enabled=True, strategy_enabled=False)

        # With _enabled suffix
        assert flags.is_enabled("reviews_enabled") is True
        assert flags.is_enabled("strategy_enabled") is False

        # Without _enabled suffix
        assert flags.is_enabled("reviews") is True
        assert flags.is_enabled("strategy") is False

    def test_all_disabled(self):
        """Test creating flags with all features disabled."""
        flags = FeatureFlags.all_disabled()
        assert flags.rag_enabled is False
        assert flags.reviews_enabled is False
        assert flags.admin_dashboard_enabled is False

    def test_all_enabled(self):
        """Test creating flags with all features enabled."""
        flags = FeatureFlags.all_enabled()
        assert flags.rag_enabled is True
        assert flags.reviews_enabled is True
        assert flags.admin_dashboard_enabled is True


class TestProductRegistry:
    """Tests for ProductRegistry."""

    def test_register_product(self, sample_product):
        """Test registering a product."""
        ProductRegistry.register(sample_product)

        result = ProductRegistry.get("test_product")
        assert result == sample_product

    def test_register_duplicate_raises(self, sample_product):
        """Test that registering duplicate product raises error."""
        ProductRegistry.register(sample_product)

        with pytest.raises(ValueError, match="already registered"):
            ProductRegistry.register(sample_product)

    def test_get_nonexistent_returns_none(self):
        """Test getting non-existent product returns None."""
        result = ProductRegistry.get("nonexistent")
        assert result is None

    def test_get_or_raise(self, sample_product):
        """Test get_or_raise with existing and non-existing products."""
        ProductRegistry.register(sample_product)

        result = ProductRegistry.get_or_raise("test_product")
        assert result == sample_product

        with pytest.raises(KeyError):
            ProductRegistry.get_or_raise("nonexistent")

    def test_list_products(self, sample_product):
        """Test listing all products."""
        ProductRegistry.register(sample_product)

        products = ProductRegistry.list_all()
        assert len(products) == 1
        assert products[0] == sample_product

    def test_list_active_products(self, sample_product):
        """Test listing active products."""
        inactive = Product(
            id="inactive",
            name="Inactive",
            description="Inactive product",
            branding=Branding(logo_text="X"),
            is_active=False,
        )
        ProductRegistry.register(sample_product)
        ProductRegistry.register(inactive)

        active = ProductRegistry.list_active()
        assert len(active) == 1
        assert active[0] == sample_product


class TestEditionRegistry:
    """Tests for EditionRegistry."""

    def test_register_edition(self, sample_edition):
        """Test registering an edition."""
        EditionRegistry.register(sample_edition)

        result = EditionRegistry.get("test_product", "v1")
        assert result == sample_edition

    def test_register_without_product_raises(self):
        """Test that registering edition without product raises error."""
        edition = Edition(
            product_id="nonexistent",
            version="v1",
            display_name="Test",
            feature_flags=FeatureFlags(),
        )

        with pytest.raises(ValueError, match="product.*not found"):
            EditionRegistry.register(edition)

    def test_active_edition_tracking(self, sample_product):
        """Test that active edition is tracked correctly."""
        ProductRegistry.register(sample_product)

        v1 = Edition(
            product_id="test_product",
            version="v1",
            display_name="V1",
            feature_flags=FeatureFlags(),
            is_active=True,
        )
        v2 = Edition(
            product_id="test_product",
            version="v2",
            display_name="V2",
            feature_flags=FeatureFlags(),
            is_active=True,
        )

        EditionRegistry.register(v1)
        EditionRegistry.register(v2)

        # V2 should be active (registered last with is_active=True)
        active = EditionRegistry.get_active("test_product")
        assert active == v2

        # V1 should be deactivated
        v1_updated = EditionRegistry.get("test_product", "v1")
        assert v1_updated.is_active is False

    def test_seal_edition(self, sample_edition):
        """Test sealing an edition through registry."""
        EditionRegistry.register(sample_edition)

        sealed = EditionRegistry.seal_edition(
            "test_product", "v1", reason="Test seal"
        )

        assert sealed.is_sealed is True
        assert sealed.sealed_reason == "Test seal"

    def test_set_active(self, sample_product):
        """Test setting active edition."""
        ProductRegistry.register(sample_product)

        v1 = Edition(
            product_id="test_product",
            version="v1",
            display_name="V1",
            feature_flags=FeatureFlags(),
            is_active=False,
        )
        v2 = Edition(
            product_id="test_product",
            version="v2",
            display_name="V2",
            feature_flags=FeatureFlags(),
            is_active=True,
        )

        EditionRegistry.register(v1)
        EditionRegistry.register(v2)

        # Set V1 as active
        EditionRegistry.set_active("test_product", "v1")

        assert EditionRegistry.get("test_product", "v1").is_active is True
        assert EditionRegistry.get("test_product", "v2").is_active is False
        assert EditionRegistry.get_active("test_product") == v1

    def test_cannot_activate_sealed(self, sample_edition):
        """Test that sealed editions cannot be activated."""
        EditionRegistry.register(sample_edition)
        EditionRegistry.seal_edition("test_product", "v1")

        with pytest.raises(ValueError, match="sealed"):
            EditionRegistry.set_active("test_product", "v1")

    def test_create_from_existing(self, sample_edition):
        """Test creating new edition from existing."""
        EditionRegistry.register(sample_edition)

        new_edition = EditionRegistry.create_from_existing(
            product_id="test_product",
            source_version="v1",
            new_version="v2",
            display_name="Test V2",
            feature_overrides={"discovery_enabled": True},
        )

        assert new_edition.version == "v2"
        assert new_edition.feature_flags.discovery_enabled is True
        assert EditionRegistry.get("test_product", "v2") == new_edition

    def test_list_sealed(self, sample_product):
        """Test listing sealed editions."""
        ProductRegistry.register(sample_product)

        v1 = Edition(
            product_id="test_product",
            version="v1",
            display_name="V1",
            feature_flags=FeatureFlags(),
            is_sealed=True,
        )
        v2 = Edition(
            product_id="test_product",
            version="v2",
            display_name="V2",
            feature_flags=FeatureFlags(),
            is_sealed=False,
        )

        EditionRegistry.register(v1)
        EditionRegistry.register(v2)

        sealed = EditionRegistry.list_sealed()
        assert len(sealed) == 1
        assert sealed[0] == v1


class TestGroundedProducts:
    """Integration tests for Grounded products."""

    def test_grounded_registration(self):
        """Test that grounded products register correctly."""
        from app.products.definitions import register_all_products

        register_all_products()

        # Check Grounded product
        grounded = ProductRegistry.get("grounded")
        assert grounded is not None
        assert grounded.name == "Grounded"
        assert grounded.is_active is True

        # Check AI Audio placeholder
        audio = ProductRegistry.get("ai_audio")
        assert audio is not None
        assert audio.is_active is False  # Placeholder

        # Check Letter+ placeholder
        letter = ProductRegistry.get("letter_plus")
        assert letter is not None
        assert letter.is_active is False  # Placeholder

    def test_grounded_editions(self):
        """Test that grounded editions register correctly."""
        from app.products.definitions import register_all_products

        register_all_products()

        # Check V1 (sealed)
        v1 = EditionRegistry.get("grounded", "v1")
        assert v1 is not None
        assert v1.is_sealed is True
        assert v1.git_reference == "a794966e77bcf1ef16ee3d93ed2a3fc5779b74a6"
        assert v1.feature_flags.discovery_enabled is False

        # Check V2 (sealed)
        v2 = EditionRegistry.get("grounded", "v2")
        assert v2 is not None
        assert v2.is_active is False
        assert v2.is_sealed is True
        assert v2.feature_flags.discovery_enabled is True

        # V3 should be the active edition
        active = EditionRegistry.get_active("grounded")
        assert active.version == "v3"

    def test_create_v4_from_v3(self):
        """Test creating V4 from V3 config."""
        from app.products.definitions import register_all_products

        register_all_products()

        # Create V4 with modified features
        v4 = EditionRegistry.create_from_existing(
            product_id="grounded",
            source_version="v3",
            new_version="v4",
            display_name="Grounded V4",
            feature_overrides={"admin_dashboard_enabled": False},
        )

        assert v4.version == "v4"
        assert v4.feature_flags.rag_enabled is True  # Inherited
        assert v4.feature_flags.admin_dashboard_enabled is False  # Overridden
        assert EditionRegistry.get_active("grounded") == v4
