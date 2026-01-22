"""Application configuration."""
from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    """Application settings from environment variables."""

    # Database
    DATABASE_URL: str

    # JWT Authentication
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # OpenAI
    OPENAI_API_KEY: str

    # Application
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    CORS_ORIGINS: str = '["http://localhost:8000"]'

    # Admin
    ADMIN_EMAIL: str
    ADMIN_PASSWORD: str

    # Toolkit
    TOOLKIT_DOCX_PATH: str = "/mnt/data/DONE2.docx"

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from JSON string."""
        return json.loads(self.CORS_ORIGINS)

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
