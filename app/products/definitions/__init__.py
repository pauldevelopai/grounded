"""
Product Definitions.

This module contains the concrete definitions for all products and their editions.
Each product has its own module file that defines:
- The product configuration (branding, navigation, etc.)
- All editions/versions of that product
- Registration logic

Products are registered when this package is imported.
"""

from app.products.definitions.toolkit import register_grounded
from app.products.definitions.audio import register_audio
from app.products.definitions.letterplus import register_letterplus


def register_all_products() -> None:
    """
    Register all products and their editions.

    This should be called during application startup to populate
    the ProductRegistry and EditionRegistry.
    """
    register_grounded()
    register_audio()
    register_letterplus()


__all__ = [
    "register_all_products",
    "register_grounded",
    "register_audio",
    "register_letterplus",
]
