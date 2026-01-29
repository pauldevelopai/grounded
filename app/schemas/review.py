"""Review Pydantic schemas."""
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID
from enum import Enum
from typing import Optional


class UseCaseTag(str, Enum):
    """Use case tags for reviews."""
    TRANSCRIPTION = "transcription"
    FACT_CHECKING = "fact-checking"
    OSINT = "OSINT"
    SOCIAL_VIDEO = "social-video"
    NEWSLETTER = "newsletter"
    TRANSLATION = "translation"
    DATA_SCRAPING = "data-scraping"
    SECURITY = "security"
    AUDIENCE_GROWTH = "audience-growth"
    OTHER = "other"


class FlagReason(str, Enum):
    """Reasons for flagging a review."""
    SPAM = "spam"
    INAPPROPRIATE = "inappropriate"
    MISLEADING = "misleading"
    OFF_TOPIC = "off-topic"
    OTHER = "other"


# Request Schemas
class ReviewCreate(BaseModel):
    """Schema for creating a review."""
    rating: int = Field(..., ge=1, le=5, description="Rating from 1 to 5 stars")
    comment: Optional[str] = Field(None, max_length=2000, description="Optional review comment")
    use_case_tag: Optional[UseCaseTag] = Field(None, description="Optional use case tag")


class ReviewUpdate(BaseModel):
    """Schema for updating a review."""
    rating: Optional[int] = Field(None, ge=1, le=5, description="Rating from 1 to 5 stars")
    comment: Optional[str] = Field(None, max_length=2000, description="Optional review comment")
    use_case_tag: Optional[UseCaseTag] = Field(None, description="Optional use case tag")


class VoteCreate(BaseModel):
    """Schema for creating a vote."""
    is_helpful: bool = Field(..., description="True for helpful, False for not helpful")


class FlagCreate(BaseModel):
    """Schema for creating a flag."""
    reason: FlagReason = Field(..., description="Reason for flagging")
    details: Optional[str] = Field(None, max_length=500, description="Additional details")


class ReviewHideRequest(BaseModel):
    """Schema for hiding a review."""
    reason: str = Field(..., min_length=1, max_length=500, description="Reason for hiding")


# Response Schemas
class ReviewAuthor(BaseModel):
    """Schema for review author info."""
    id: UUID
    username: Optional[str] = None
    display_name: Optional[str] = None

    class Config:
        from_attributes = True


class ReviewResponse(BaseModel):
    """Schema for review response."""
    id: UUID
    tool_slug: str
    rating: int
    comment: Optional[str] = None
    use_case_tag: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    author: ReviewAuthor
    helpful_count: int = 0
    not_helpful_count: int = 0
    user_vote: Optional[bool] = None
    is_own_review: bool = False
    is_hidden: bool = False

    class Config:
        from_attributes = True


class ReviewListResponse(BaseModel):
    """Schema for list of reviews with stats."""
    reviews: list[ReviewResponse]
    total: int
    average_rating: Optional[float] = None
    rating_distribution: dict[str, int] = Field(
        default_factory=lambda: {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    )


class VoteResponse(BaseModel):
    """Schema for vote response."""
    helpful_count: int
    not_helpful_count: int
    user_vote: Optional[bool] = None


class ToolRatingStats(BaseModel):
    """Schema for tool rating statistics."""
    average_rating: Optional[float] = None
    total_reviews: int = 0
    distribution: dict[str, int] = Field(
        default_factory=lambda: {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    )
    recent_trend: Optional[float] = None


class FlagResponse(BaseModel):
    """Schema for flag response."""
    id: UUID
    reason: str
    details: Optional[str] = None
    created_at: datetime
    user_id: UUID

    class Config:
        from_attributes = True


class AdminReviewResponse(BaseModel):
    """Schema for admin review response with extra info."""
    id: UUID
    tool_slug: str
    rating: int
    comment: Optional[str] = None
    use_case_tag: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    author: ReviewAuthor
    user_email: str
    helpful_count: int = 0
    not_helpful_count: int = 0
    is_hidden: bool = False
    hidden_reason: Optional[str] = None
    flag_count: int = 0

    class Config:
        from_attributes = True
