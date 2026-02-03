"""Learning profile service for personalized AI recommendations."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.auth import User
from app.models.learning_profile import UserLearningProfile
from app.models.toolkit import UserActivity
from app.settings import settings

logger = logging.getLogger(__name__)


# How often to regenerate the AI profile summary
SUMMARY_STALE_DAYS = 7
# How many new activities before regenerating summary
SUMMARY_ACTIVITY_THRESHOLD = 20


def get_or_create_profile(db: Session, user_id: str) -> UserLearningProfile:
    """Get or create a learning profile for a user."""
    profile = db.query(UserLearningProfile).filter(
        UserLearningProfile.user_id == user_id
    ).first()

    if not profile:
        profile = UserLearningProfile(
            user_id=user_id,
            preferred_clusters={},
            tool_interests={},
            searched_topics=[],
            strategy_feedback=[],
            dismissed_tools=[],
            favorited_tools=[],
            last_activity_count={},
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

    return profile


def update_learning_profile(db: Session, user_id: str) -> UserLearningProfile:
    """
    Aggregate recent activity into the learning profile.

    This analyzes the user's activity patterns and updates their
    profile with learned preferences.
    """
    profile = get_or_create_profile(db, user_id)

    # Get recent activities (last 30 days)
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    activities = db.query(UserActivity).filter(
        UserActivity.user_id == user_id,
        UserActivity.created_at >= thirty_days_ago
    ).order_by(desc(UserActivity.created_at)).all()

    # Initialize tracking dicts
    cluster_counts = {}
    tool_views = {}
    search_queries = []

    for activity in activities:
        details = activity.details or {}

        # Track cluster browsing
        if activity.activity_type == "browse" and details.get("cluster"):
            cluster = details["cluster"]
            cluster_counts[cluster] = cluster_counts.get(cluster, 0) + 1

        elif activity.activity_type == "tool_finder" and details.get("need"):
            # Map need to cluster interest
            need = details["need"]
            cluster_counts[need] = cluster_counts.get(need, 0) + 1

        # Track tool views
        elif activity.activity_type == "tool_view" and details.get("tool_slug"):
            tool_slug = details["tool_slug"]
            if tool_slug not in tool_views:
                tool_views[tool_slug] = {"viewed": 0, "time_spent": 0}
            tool_views[tool_slug]["viewed"] += 1

        # Track tool time spent
        elif activity.activity_type == "tool_time_spent" and details.get("tool_slug"):
            tool_slug = details["tool_slug"]
            duration = details.get("duration_seconds", 0)
            if tool_slug not in tool_views:
                tool_views[tool_slug] = {"viewed": 0, "time_spent": 0}
            tool_views[tool_slug]["time_spent"] += duration

        # Track searches
        elif activity.activity_type == "tool_search" and activity.query:
            search_queries.append({
                "query": activity.query,
                "timestamp": activity.created_at.isoformat(),
                "results_clicked": details.get("results_clicked", [])
            })

        # Track favorites
        elif activity.activity_type == "tool_favorited" and details.get("tool_slug"):
            tool_slug = details["tool_slug"]
            if tool_slug not in (profile.favorited_tools or []):
                favorited = profile.favorited_tools or []
                favorited.append(tool_slug)
                profile.favorited_tools = favorited
                if tool_slug in tool_views:
                    tool_views[tool_slug]["favorited"] = True

        # Track dismissals
        elif activity.activity_type == "tool_dismissed" and details.get("tool_slug"):
            tool_slug = details["tool_slug"]
            if tool_slug not in (profile.dismissed_tools or []):
                dismissed = profile.dismissed_tools or []
                dismissed.append(tool_slug)
                profile.dismissed_tools = dismissed

        # Track strategy feedback
        elif activity.activity_type == "strategy_feedback" and details.get("strategy_id"):
            feedback = profile.strategy_feedback or []
            feedback.append({
                "strategy_id": details["strategy_id"],
                "helpful": details.get("helpful", False),
                "implemented": details.get("implemented", []),
                "timestamp": activity.created_at.isoformat()
            })
            profile.strategy_feedback = feedback

    # Normalize cluster counts to scores (0.0-1.0)
    if cluster_counts:
        max_count = max(cluster_counts.values())
        profile.preferred_clusters = {
            k: round(v / max_count, 2)
            for k, v in cluster_counts.items()
        }

    # Update tool interests
    existing_interests = profile.tool_interests or {}
    for tool_slug, data in tool_views.items():
        if tool_slug in existing_interests:
            existing_interests[tool_slug]["viewed"] = existing_interests[tool_slug].get("viewed", 0) + data["viewed"]
            existing_interests[tool_slug]["time_spent"] = existing_interests[tool_slug].get("time_spent", 0) + data["time_spent"]
        else:
            existing_interests[tool_slug] = data
    profile.tool_interests = existing_interests

    # Update searched topics (keep last 50)
    existing_searches = profile.searched_topics or []
    existing_searches = search_queries + existing_searches
    profile.searched_topics = existing_searches[:50]

    # Track activity count for summary regeneration
    profile.last_activity_count = {
        "total": len(activities),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)

    return profile


def should_regenerate_summary(profile: UserLearningProfile) -> bool:
    """Determine if the profile summary needs to be regenerated."""
    # No summary yet
    if not profile.profile_summary or not profile.last_summary_at:
        return True

    # Summary is stale (older than SUMMARY_STALE_DAYS)
    if profile.last_summary_at:
        stale_threshold = datetime.now(timezone.utc) - timedelta(days=SUMMARY_STALE_DAYS)
        if profile.last_summary_at < stale_threshold:
            return True

    # Significant new activity
    activity_count = profile.last_activity_count or {}
    total_activities = activity_count.get("total", 0)
    # If we've accumulated many new activities, regenerate
    # This is a simplification - in production you'd track delta
    if total_activities >= SUMMARY_ACTIVITY_THRESHOLD:
        return True

    return False


async def generate_profile_summary(db: Session, user: User, profile: UserLearningProfile) -> str:
    """
    Use LLM to create a narrative summary of user's patterns and needs.

    This summary is used as context when generating personalized strategies.
    """
    from openai import OpenAI

    # Build context from profile data
    top_clusters = []
    if profile.preferred_clusters:
        sorted_clusters = sorted(
            profile.preferred_clusters.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        top_clusters = [c[0] for c in sorted_clusters]

    top_tools = []
    if profile.tool_interests:
        # Sort by view count + time spent
        sorted_tools = sorted(
            profile.tool_interests.items(),
            key=lambda x: x[1].get("viewed", 0) + x[1].get("time_spent", 0) / 60,
            reverse=True
        )[:5]
        top_tools = [t[0] for t in sorted_tools]

    recent_searches = []
    if profile.searched_topics:
        recent_searches = [s["query"] for s in profile.searched_topics[:10]]

    # Build the prompt
    context = f"""User Profile:
- Organisation Type: {user.organisation_type or 'Not specified'}
- Role: {user.role or 'Not specified'}
- AI Experience Level: {user.ai_experience_level or 'Not specified'}
- Country: {user.country or 'Not specified'}
- Risk Level: {user.risk_level or 'Not specified'}
- Data Sensitivity: {user.data_sensitivity or 'Not specified'}
- Budget: {user.budget or 'Not specified'}

Activity Patterns:
- Top Interests (clusters): {', '.join(top_clusters) if top_clusters else 'None yet'}
- Most Viewed Tools: {', '.join(top_tools) if top_tools else 'None yet'}
- Recent Searches: {', '.join(recent_searches) if recent_searches else 'None yet'}
- Dismissed Tools: {len(profile.dismissed_tools or [])} tools
- Favorited Tools: {', '.join(profile.favorited_tools or []) if profile.favorited_tools else 'None'}

Strategy Feedback:
- Feedback given: {len(profile.strategy_feedback or [])} times
"""

    prompt = f"""Based on this user's activity and profile, write a 2-3 sentence summary
of their needs, preferences, and what they're looking for in AI tools.

{context}

Write in third person (e.g., "This user..."). Be specific about their likely needs.
If there's limited activity data, focus on their profile fields."""

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    try:
        response = client.chat.completions.create(
            model=settings.OPENAI_CHAT_MODEL,
            temperature=0.3,
            max_tokens=200,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that creates concise user profile summaries for an AI editorial toolkit. Focus on journalistic needs and practical requirements."
                },
                {"role": "user", "content": prompt}
            ]
        )
        summary = response.choices[0].message.content
        return summary.strip()

    except Exception as e:
        logger.error(f"Failed to generate profile summary: {e}")
        # Return a basic summary if LLM fails
        return f"User is a {user.role or 'journalist'} at a {user.organisation_type or 'newsroom'} with {user.ai_experience_level or 'some'} AI experience."


async def get_personalized_context(db: Session, user: User) -> Dict[str, Any]:
    """
    Build rich context for strategy/recommendation generation.

    This returns data that can be used to personalize AI-generated content.
    """
    profile = get_or_create_profile(db, str(user.id))

    # Update profile with recent activity
    profile = update_learning_profile(db, str(user.id))

    # Regenerate summary if needed
    if should_regenerate_summary(profile):
        profile.profile_summary = await generate_profile_summary(db, user, profile)
        profile.last_summary_at = datetime.now(timezone.utc)
        db.commit()

    # Get top interests
    top_interests = []
    if profile.preferred_clusters:
        sorted_clusters = sorted(
            profile.preferred_clusters.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        top_interests = [{"cluster": c[0], "score": c[1]} for c in sorted_clusters]

    # Infer learning style from activity patterns
    learning_style = infer_learning_style(profile)

    return {
        "profile_summary": profile.profile_summary,
        "top_interests": top_interests,
        "avoided_tools": profile.dismissed_tools or [],
        "favorited_tools": profile.favorited_tools or [],
        "learning_style": learning_style,
        "recent_searches": [s["query"] for s in (profile.searched_topics or [])[:5]],
        "strategy_feedback_count": len(profile.strategy_feedback or []),
    }


def infer_learning_style(profile: UserLearningProfile) -> str:
    """
    Infer user's learning style from their activity patterns.

    Returns a descriptive string for the LLM to use as context.
    """
    tool_interests = profile.tool_interests or {}
    searches = profile.searched_topics or []
    favorites = profile.favorited_tools or []

    # Calculate engagement metrics
    total_views = sum(t.get("viewed", 0) for t in tool_interests.values())
    total_time = sum(t.get("time_spent", 0) for t in tool_interests.values())

    if not total_views and not searches:
        return "new user with limited activity"

    # Deep explorer: lots of time on individual tools
    if total_time > 300 and total_views < 20:  # 5+ minutes, few tools
        return "deep explorer who spends time understanding each tool thoroughly"

    # Broad scanner: many views, less time each
    if total_views > 30 and total_time < 300:
        return "broad scanner who reviews many options before deciding"

    # Search-driven: lots of searches
    if len(searches) > 10:
        return "search-driven user who looks for specific solutions"

    # Bookmark collector: many favorites
    if len(favorites) > 5:
        return "collector who saves tools for later evaluation"

    return "standard explorer with balanced browsing patterns"


def track_tool_interaction(
    db: Session,
    user_id: str,
    tool_slug: str,
    interaction_type: str,
    details: Optional[Dict[str, Any]] = None
) -> None:
    """
    Track a user's interaction with a tool for learning purposes.

    Args:
        db: Database session
        user_id: User ID
        tool_slug: Tool slug
        interaction_type: One of: view, dismiss, favorite, time_spent
        details: Additional details (e.g., duration_seconds for time_spent)
    """
    activity_details = {"tool_slug": tool_slug}
    if details:
        activity_details.update(details)

    activity = UserActivity(
        user_id=user_id,
        activity_type=f"tool_{interaction_type}",
        details=activity_details
    )
    db.add(activity)
    db.commit()


def track_strategy_feedback(
    db: Session,
    user_id: str,
    strategy_id: str,
    helpful: bool,
    implemented_tools: Optional[List[str]] = None
) -> None:
    """
    Track user feedback on a generated strategy.

    Args:
        db: Database session
        user_id: User ID
        strategy_id: Strategy plan ID
        helpful: Whether the strategy was helpful
        implemented_tools: List of tool slugs the user implemented
    """
    activity = UserActivity(
        user_id=user_id,
        activity_type="strategy_feedback",
        details={
            "strategy_id": strategy_id,
            "helpful": helpful,
            "implemented": implemented_tools or []
        }
    )
    db.add(activity)
    db.commit()
