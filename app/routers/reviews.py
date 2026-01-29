"""Reviews API routes for tool ratings and reviews."""
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.db import get_db
from app.models.auth import User
from app.models.review import ToolReview, ReviewVote, ReviewFlag
from app.dependencies import get_current_user, require_auth
from app.schemas.review import (
    ReviewCreate, ReviewUpdate, VoteCreate, FlagCreate,
    ReviewResponse, ReviewListResponse, VoteResponse,
    ToolRatingStats, ReviewAuthor
)
from app.services.kit_loader import get_tool


router = APIRouter(prefix="/api/reviews", tags=["reviews"])


def get_review_response(
    review: ToolReview,
    db: Session,
    current_user: Optional[User] = None
) -> ReviewResponse:
    """Build ReviewResponse with computed fields."""
    # Count votes
    helpful_count = db.query(func.count(ReviewVote.id)).filter(
        ReviewVote.review_id == review.id,
        ReviewVote.is_helpful == True
    ).scalar() or 0

    not_helpful_count = db.query(func.count(ReviewVote.id)).filter(
        ReviewVote.review_id == review.id,
        ReviewVote.is_helpful == False
    ).scalar() or 0

    # Get user's vote if authenticated
    user_vote = None
    is_own_review = False
    if current_user:
        vote = db.query(ReviewVote).filter(
            ReviewVote.review_id == review.id,
            ReviewVote.user_id == current_user.id
        ).first()
        if vote:
            user_vote = vote.is_helpful
        is_own_review = review.user_id == current_user.id

    # Build author info
    author = ReviewAuthor(
        id=review.user.id,
        username=getattr(review.user, 'username', None),
        display_name=getattr(review.user, 'display_name', None)
    )

    return ReviewResponse(
        id=review.id,
        tool_slug=review.tool_slug,
        rating=review.rating,
        comment=review.comment,
        use_case_tag=review.use_case_tag,
        created_at=review.created_at,
        updated_at=review.updated_at,
        author=author,
        helpful_count=helpful_count,
        not_helpful_count=not_helpful_count,
        user_vote=user_vote,
        is_own_review=is_own_review,
        is_hidden=review.is_hidden
    )


# ============================================================================
# PUBLIC ENDPOINTS
# ============================================================================

@router.get("/tools/{slug}", response_model=ReviewListResponse)
async def list_reviews(
    slug: str,
    sort: str = "recent",
    page: int = 1,
    per_page: int = 10,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user)
):
    """
    List reviews for a tool with sorting and pagination.

    Sort options: recent, helpful, rating_high, rating_low
    """
    # Verify tool exists
    tool = get_tool(slug)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    # Base query - exclude hidden reviews for non-admins
    query = db.query(ToolReview).filter(ToolReview.tool_slug == slug)
    if not user or not user.is_admin:
        query = query.filter(ToolReview.is_hidden == False)

    # Apply sorting
    if sort == "helpful":
        # Order by net helpful votes (helpful - not helpful)
        helpful_subq = (
            db.query(
                ReviewVote.review_id,
                func.sum(func.cast(ReviewVote.is_helpful, db.bind.dialect.name == 'postgresql' and 'integer' or None)).label('helpful'),
                func.sum(func.cast(~ReviewVote.is_helpful, db.bind.dialect.name == 'postgresql' and 'integer' or None)).label('not_helpful')
            )
            .group_by(ReviewVote.review_id)
            .subquery()
        )
        query = query.outerjoin(helpful_subq, ToolReview.id == helpful_subq.c.review_id)
        query = query.order_by(
            desc(func.coalesce(helpful_subq.c.helpful, 0) - func.coalesce(helpful_subq.c.not_helpful, 0)),
            desc(ToolReview.created_at)
        )
    elif sort == "rating_high":
        query = query.order_by(desc(ToolReview.rating), desc(ToolReview.created_at))
    elif sort == "rating_low":
        query = query.order_by(ToolReview.rating, desc(ToolReview.created_at))
    else:  # recent
        query = query.order_by(desc(ToolReview.created_at))

    # Get total count
    total = db.query(func.count(ToolReview.id)).filter(
        ToolReview.tool_slug == slug,
        ToolReview.is_hidden == False
    ).scalar() or 0

    # Calculate rating stats
    stats_query = db.query(ToolReview).filter(
        ToolReview.tool_slug == slug,
        ToolReview.is_hidden == False
    )

    average_rating = db.query(func.avg(ToolReview.rating)).filter(
        ToolReview.tool_slug == slug,
        ToolReview.is_hidden == False
    ).scalar()

    # Rating distribution
    distribution = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    dist_query = (
        db.query(ToolReview.rating, func.count(ToolReview.id))
        .filter(ToolReview.tool_slug == slug, ToolReview.is_hidden == False)
        .group_by(ToolReview.rating)
        .all()
    )
    for rating, count in dist_query:
        distribution[str(rating)] = count

    # Paginate
    offset = (page - 1) * per_page
    reviews = query.offset(offset).limit(per_page).all()

    # Build response
    review_responses = [get_review_response(r, db, user) for r in reviews]

    return ReviewListResponse(
        reviews=review_responses,
        total=total,
        average_rating=round(average_rating, 1) if average_rating else None,
        rating_distribution=distribution
    )


@router.get("/tools/{slug}/stats", response_model=ToolRatingStats)
async def get_rating_stats(
    slug: str,
    db: Session = Depends(get_db)
):
    """Get aggregate rating stats for a tool."""
    # Verify tool exists
    tool = get_tool(slug)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    # Total reviews
    total = db.query(func.count(ToolReview.id)).filter(
        ToolReview.tool_slug == slug,
        ToolReview.is_hidden == False
    ).scalar() or 0

    # Average rating
    average = db.query(func.avg(ToolReview.rating)).filter(
        ToolReview.tool_slug == slug,
        ToolReview.is_hidden == False
    ).scalar()

    # Distribution
    distribution = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    dist_query = (
        db.query(ToolReview.rating, func.count(ToolReview.id))
        .filter(ToolReview.tool_slug == slug, ToolReview.is_hidden == False)
        .group_by(ToolReview.rating)
        .all()
    )
    for rating, count in dist_query:
        distribution[str(rating)] = count

    return ToolRatingStats(
        average_rating=round(average, 1) if average else None,
        total_reviews=total,
        distribution=distribution
    )


# ============================================================================
# AUTHENTICATED ENDPOINTS
# ============================================================================

@router.post("/tools/{slug}", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
async def create_review(
    slug: str,
    review_data: ReviewCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Create a review for a tool. One review per user per tool."""
    # Verify tool exists
    tool = get_tool(slug)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    # Check if user already has a review
    existing = db.query(ToolReview).filter(
        ToolReview.user_id == user.id,
        ToolReview.tool_slug == slug
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="You already have a review for this tool. Please edit your existing review."
        )

    # Create review
    review = ToolReview(
        user_id=user.id,
        tool_slug=slug,
        rating=review_data.rating,
        comment=review_data.comment,
        use_case_tag=review_data.use_case_tag.value if review_data.use_case_tag else None
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    return get_review_response(review, db, user)


@router.get("/tools/{slug}/my-review", response_model=Optional[ReviewResponse])
async def get_my_review(
    slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Get the current user's review for a tool, if it exists."""
    review = db.query(ToolReview).filter(
        ToolReview.user_id == user.id,
        ToolReview.tool_slug == slug
    ).first()

    if not review:
        return None

    return get_review_response(review, db, user)


@router.put("/tools/{slug}/reviews/{review_id}", response_model=ReviewResponse)
async def update_review(
    slug: str,
    review_id: UUID,
    review_data: ReviewUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Update own review."""
    review = db.query(ToolReview).filter(
        ToolReview.id == review_id,
        ToolReview.tool_slug == slug
    ).first()

    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    if review.user_id != user.id:
        raise HTTPException(status_code=403, detail="Cannot edit another user's review")

    # Update fields if provided
    if review_data.rating is not None:
        review.rating = review_data.rating
    if review_data.comment is not None:
        review.comment = review_data.comment
    if review_data.use_case_tag is not None:
        review.use_case_tag = review_data.use_case_tag.value

    db.commit()
    db.refresh(review)

    return get_review_response(review, db, user)


@router.delete("/tools/{slug}/reviews/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_review(
    slug: str,
    review_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Delete own review."""
    review = db.query(ToolReview).filter(
        ToolReview.id == review_id,
        ToolReview.tool_slug == slug
    ).first()

    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    if review.user_id != user.id and not user.is_admin:
        raise HTTPException(status_code=403, detail="Cannot delete another user's review")

    db.delete(review)
    db.commit()


@router.post("/reviews/{review_id}/vote", response_model=VoteResponse)
async def vote_review(
    review_id: UUID,
    vote_data: VoteCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Vote on a review. Toggle behavior: same vote removes it, different vote changes it."""
    review = db.query(ToolReview).filter(ToolReview.id == review_id).first()

    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    if review.user_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot vote on your own review")

    # Check for existing vote
    existing_vote = db.query(ReviewVote).filter(
        ReviewVote.review_id == review_id,
        ReviewVote.user_id == user.id
    ).first()

    user_vote = None

    if existing_vote:
        if existing_vote.is_helpful == vote_data.is_helpful:
            # Same vote - remove it (toggle off)
            db.delete(existing_vote)
            user_vote = None
        else:
            # Different vote - update it
            existing_vote.is_helpful = vote_data.is_helpful
            user_vote = vote_data.is_helpful
    else:
        # Create new vote
        new_vote = ReviewVote(
            review_id=review_id,
            user_id=user.id,
            is_helpful=vote_data.is_helpful
        )
        db.add(new_vote)
        user_vote = vote_data.is_helpful

    db.commit()

    # Get updated counts
    helpful_count = db.query(func.count(ReviewVote.id)).filter(
        ReviewVote.review_id == review_id,
        ReviewVote.is_helpful == True
    ).scalar() or 0

    not_helpful_count = db.query(func.count(ReviewVote.id)).filter(
        ReviewVote.review_id == review_id,
        ReviewVote.is_helpful == False
    ).scalar() or 0

    return VoteResponse(
        helpful_count=helpful_count,
        not_helpful_count=not_helpful_count,
        user_vote=user_vote
    )


@router.post("/reviews/{review_id}/flag", status_code=status.HTTP_201_CREATED)
async def flag_review(
    review_id: UUID,
    flag_data: FlagCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Flag a review for moderation."""
    review = db.query(ToolReview).filter(ToolReview.id == review_id).first()

    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    if review.user_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot flag your own review")

    # Check if already flagged by this user
    existing_flag = db.query(ReviewFlag).filter(
        ReviewFlag.review_id == review_id,
        ReviewFlag.user_id == user.id
    ).first()

    if existing_flag:
        raise HTTPException(status_code=400, detail="You have already flagged this review")

    # Create flag
    flag = ReviewFlag(
        review_id=review_id,
        user_id=user.id,
        reason=flag_data.reason.value,
        details=flag_data.details
    )
    db.add(flag)
    db.commit()

    return {"message": "Review flagged for moderation"}
