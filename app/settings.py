"""Application settings with production hardening."""
from pydantic_settings import BaseSettings
from pydantic import field_validator, model_validator
from typing import Literal, Optional
import secrets


class Settings(BaseSettings):
    """Application configuration from environment variables."""

    # Environment
    ENV: Literal["dev", "staging", "prod"] = "dev"

    # Database
    DATABASE_URL: str

    # Security
    SECRET_KEY: str = secrets.token_urlsafe(32)  # Default for dev only
    SESSION_COOKIE_NAME: str = "session"
    SESSION_MAX_AGE: int = 30 * 24 * 60 * 60  # 30 days
    COOKIE_SECURE: bool = False  # Auto-set based on ENV
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    COOKIE_HTTPONLY: bool = True

    # CSRF Protection
    CSRF_SECRET_KEY: Optional[str] = None  # Auto-generated if not provided
    CSRF_TOKEN_EXPIRY: int = 3600  # 1 hour

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_AUTH_REQUESTS: int = 5  # requests per window
    RATE_LIMIT_AUTH_WINDOW: int = 60  # seconds
    RATE_LIMIT_RAG_REQUESTS: int = 20  # requests per window
    RATE_LIMIT_RAG_WINDOW: int = 60  # seconds

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["json", "text"] = "json"  # JSON for production
    LOG_FILE: Optional[str] = None  # Optional file logging

    # Embedding Provider Configuration
    EMBEDDING_PROVIDER: Literal["openai", "local_stub"] = "openai"
    OPENAI_API_KEY: Optional[str] = None
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 1536

    # OpenAI Chat Configuration
    OPENAI_CHAT_MODEL: str = "gpt-4o-mini"
    OPENAI_CHAT_TEMPERATURE: float = 0.1

    # RAG Configuration
    RAG_TOP_K: int = 5
    RAG_SIMILARITY_THRESHOLD: float = 0.3
    RAG_MAX_CONTEXT_LENGTH: int = 4000

    # Admin (dev/staging only - should use proper admin creation in prod)
    ADMIN_PASSWORD: Optional[str] = None

    # Discovery Pipeline Configuration
    DISCOVERY_ENABLED: bool = True
    DISCOVERY_API_KEY: Optional[str] = None  # For cron authentication

    # GitHub Discovery
    GITHUB_TOKEN: Optional[str] = None  # For higher rate limits
    GITHUB_MIN_STARS: int = 100

    # Product Hunt Discovery
    PRODUCTHUNT_API_KEY: Optional[str] = None
    PRODUCTHUNT_API_SECRET: Optional[str] = None

    # Discovery Rate Limits
    DISCOVERY_RATE_LIMIT_DELAY: float = 2.0  # seconds between requests

    # Discovery Pipeline Timeouts
    DISCOVERY_PIPELINE_TIMEOUT: int = 1800  # 30 minutes max for entire pipeline
    DISCOVERY_PROGRESS_STALE_MINUTES: int = 5  # Mark failed if no update in 5 min

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"

    @model_validator(mode='after')
    def validate_production_settings(self):
        """Validate production-specific requirements."""
        # In production, require explicit SECRET_KEY
        if self.ENV == "prod":
            if self.SECRET_KEY == secrets.token_urlsafe(32) or len(self.SECRET_KEY) < 32:
                raise ValueError(
                    "SECRET_KEY must be explicitly set in production (min 32 characters). "
                    "Generate with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
                )

            # Warn if secure cookies not enabled (requires HTTPS)
            # COOKIE_SECURE can be set to false in .env when HTTPS is not configured
            if self.COOKIE_SAMESITE == "none" and not self.COOKIE_SECURE:
                raise ValueError(
                    "COOKIE_SAMESITE='none' requires COOKIE_SECURE=True. "
                    "Use 'lax' or 'strict' for production."
                )

        # Auto-generate CSRF secret if not provided
        if not self.CSRF_SECRET_KEY:
            self.CSRF_SECRET_KEY = secrets.token_urlsafe(32)

        return self

    @field_validator('DATABASE_URL')
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate DATABASE_URL is provided."""
        if not v:
            raise ValueError(
                "DATABASE_URL is required. "
                "Example: postgresql://user:password@localhost:5432/dbname"
            )
        return v

    @field_validator('OPENAI_API_KEY')
    @classmethod
    def validate_openai_key(cls, v: Optional[str], info) -> Optional[str]:
        """Validate OpenAI API key if provider is openai."""
        # Note: we can't access other fields in field_validator,
        # so the full validation happens in validate_embedding_config
        return v

    def validate_embedding_config(self) -> None:
        """
        Validate embedding configuration at startup.

        Raises:
            ValueError: If OpenAI provider is selected but API key is missing
        """
        if self.EMBEDDING_PROVIDER == "openai":
            if not self.OPENAI_API_KEY or self.OPENAI_API_KEY.startswith("sk-your"):
                raise ValueError(
                    "EMBEDDING_PROVIDER is set to 'openai' but OPENAI_API_KEY is not configured. "
                    "Either set a valid OPENAI_API_KEY or change EMBEDDING_PROVIDER to 'local_stub' for testing."
                )

    def validate_required_for_env(self) -> None:
        """
        Validate all required settings for the current environment.

        Raises:
            ValueError: If required settings are missing
        """
        errors = []

        # Always required
        if not self.DATABASE_URL:
            errors.append("DATABASE_URL is required")

        # Production requirements
        if self.ENV == "prod":
            if not self.SECRET_KEY or len(self.SECRET_KEY) < 32:
                errors.append("SECRET_KEY must be set with min 32 characters in production")

            if self.ADMIN_PASSWORD:
                errors.append(
                    "ADMIN_PASSWORD should not be set in production. "
                    "Create admin users through proper channels."
                )

        # Embedding provider requirements
        if self.EMBEDDING_PROVIDER == "openai" and not self.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai")

        if errors:
            raise ValueError(
                "Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )


# Singleton settings instance
settings = Settings()
