"""Authentication schemas."""
from pydantic import BaseModel


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str


class RefreshTokenRequest(BaseModel):
    """Request to refresh access token."""
    refresh_token: str
