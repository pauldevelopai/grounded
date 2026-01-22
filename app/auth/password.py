"""Password hashing utilities using Argon2."""
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# Initialize Argon2 password hasher with secure defaults
ph = PasswordHasher()


def hash_password(password: str) -> str:
    """
    Hash a password using Argon2.

    Args:
        password: Plain text password to hash

    Returns:
        Hashed password string
    """
    return ph.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash.

    Args:
        password: Plain text password to verify
        hashed_password: Hashed password to check against

    Returns:
        True if password matches, False otherwise
    """
    try:
        ph.verify(hashed_password, password)
        # Check if the password needs rehashing (parameters changed)
        if ph.check_needs_rehash(hashed_password):
            # In production, you would rehash and update the database here
            pass
        return True
    except VerifyMismatchError:
        return False
