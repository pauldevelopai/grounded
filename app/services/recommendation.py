"""Personalized tool recommendation service.

Recommends tools based on user profile and activity, provides tailored
implementation guidance, and grounds all recommendations with citations.

Recommendations rotate based on:
- Tools recently shown (penalized to promote variety)
- User activity signals (searches, views, browsing)
- Time-based diversity (different recommendations on repeat visits)
"""
import hashlib
import random
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.models.auth import User
from app.models.toolkit import UserActivity
from app.models.review import ToolReview
from app.models.playbook import ToolPlaybook, PlaybookSource
from app.services.kit_loader import get_all_tools, get_tool, search_tools
from app.schemas.recommendation import (
    UserContext, ToolRecommendation, TailoredGuidance,
    Citation, CitationType, ScoreBreakdown, TrainingPlan, RolloutApproach
)

# Maximum recommendations to show at once
MAX_RECOMMENDATIONS = 8

# How long before a shown recommendation can reappear (hours)
ROTATION_COOLDOWN_HOURS = 24


# Constraint mappings from user profile to CDI limits
BUDGET_TO_MAX_COST = {
    "minimal": 2,
    "small": 4,
    "medium": 6,
    "large": 10,
}

EXPERIENCE_TO_MAX_DIFFICULTY = {
    "beginner": 3,
    "intermediate": 6,
    "advanced": 10,
}

DATA_SENSITIVITY_TO_MAX_INVASIVENESS = {
    "regulated": 2,
    "pii": 4,
    "internal": 6,
    "public": 10,
}


def get_recently_shown_recommendations(db: Session, user_id: UUID, hours: int = ROTATION_COOLDOWN_HOURS) -> list[str]:
    """Get tool slugs that were recently shown in recommendations.

    Args:
        db: Database session
        user_id: User ID
        hours: How far back to look

    Returns:
        List of tool slugs that were recently recommended
    """
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    recent = db.query(UserActivity).filter(
        UserActivity.user_id == user_id,
        UserActivity.activity_type == "recommendation_shown",
        UserActivity.created_at >= cutoff
    ).all()

    shown_slugs = []
    for activity in recent:
        if activity.details and "tool_slugs" in activity.details:
            shown_slugs.extend(activity.details["tool_slugs"])

    return list(set(shown_slugs))


def record_recommendations_shown(db: Session, user_id: UUID, tool_slugs: list[str]) -> None:
    """Record which recommendations were shown to the user.

    Args:
        db: Database session
        user_id: User ID
        tool_slugs: List of tool slugs that were shown
    """
    activity = UserActivity(
        user_id=user_id,
        activity_type="recommendation_shown",
        details={"tool_slugs": tool_slugs}
    )
    db.add(activity)
    db.commit()


def get_diversity_seed(user_id: UUID) -> int:
    """Generate a time-based seed for diversity that changes periodically.

    Uses hour of day + user_id to create variation that:
    - Changes every hour for the same user
    - Is different for different users at the same time

    Args:
        user_id: User UUID

    Returns:
        Integer seed for random operations
    """
    now = datetime.utcnow()
    # Change seed every 4 hours
    time_bucket = now.hour // 4
    day_of_year = now.timetuple().tm_yday

    # Combine time bucket with user_id for unique-per-user diversity
    seed_string = f"{user_id}-{day_of_year}-{time_bucket}"
    return int(hashlib.md5(seed_string.encode()).hexdigest()[:8], 16)


def build_user_context(db: Session, user: User) -> UserContext:
    """Build aggregated user context from profile and activity.

    Args:
        db: Database session
        user: The user to build context for

    Returns:
        UserContext with profile data and activity signals
    """
    # Parse use_cases from comma-separated string
    use_cases = []
    if user.use_cases:
        use_cases = [uc.strip() for uc in user.use_cases.split(",") if uc.strip()]

    # Compute CDI constraints from profile
    max_cost = BUDGET_TO_MAX_COST.get(user.budget, 10)
    max_difficulty = EXPERIENCE_TO_MAX_DIFFICULTY.get(user.ai_experience_level, 10)
    max_invasiveness = DATA_SENSITIVITY_TO_MAX_INVASIVENESS.get(user.data_sensitivity, 10)

    # Get recent activity signals (last 30 days worth)
    recent_activities = db.query(UserActivity).filter(
        UserActivity.user_id == user.id
    ).order_by(desc(UserActivity.created_at)).limit(100).all()

    searched_queries = []
    browsed_clusters = []
    viewed_tools = []

    for activity in recent_activities:
        if activity.activity_type == "tool_search" and activity.query:
            if activity.query not in searched_queries:
                searched_queries.append(activity.query)
        elif activity.activity_type == "tool_finder" and activity.details:
            need = activity.details.get("need")
            if need and need not in browsed_clusters:
                browsed_clusters.append(need)
        elif activity.activity_type == "tool_view" and activity.details:
            tool_slug = activity.details.get("tool_slug")
            if tool_slug and tool_slug not in viewed_tools:
                viewed_tools.append(tool_slug)
        elif activity.activity_type == "browse" and activity.details:
            cluster = activity.details.get("cluster")
            if cluster and cluster not in browsed_clusters:
                browsed_clusters.append(cluster)

    # Get tools user has reviewed
    reviewed_tools = db.query(ToolReview.tool_slug).filter(
        ToolReview.user_id == user.id,
        ToolReview.is_hidden == False
    ).distinct().all()
    reviewed_tool_slugs = [r[0] for r in reviewed_tools]

    return UserContext(
        user_id=user.id,
        organisation_type=user.organisation_type,
        role=user.role,
        country=user.country,
        ai_experience_level=user.ai_experience_level,
        budget=user.budget,
        risk_level=user.risk_level,
        data_sensitivity=user.data_sensitivity,
        deployment_pref=user.deployment_pref,
        use_cases=use_cases,
        searched_queries=searched_queries[:10],
        browsed_clusters=browsed_clusters[:10],
        viewed_tools=viewed_tools[:20],
        reviewed_tools=reviewed_tool_slugs,
        max_cost=max_cost,
        max_difficulty=max_difficulty,
        max_invasiveness=max_invasiveness,
    )


def score_tool_for_user(
    tool: dict,
    context: UserContext,
    matching_reviews: list[dict],
) -> tuple[float, ScoreBreakdown]:
    """Score a tool for a specific user context.

    Scoring weights:
    - CDI Fit: 30%
    - Use Case Match: 25%
    - Review Signal: 20%
    - Activity Relevance: 15%
    - Profile Fit: 10%

    Args:
        tool: Tool data dictionary
        context: User context
        matching_reviews: Reviews from similar users

    Returns:
        Tuple of (total_score, breakdown)
    """
    cdi = tool.get("cdi_scores", {})
    cost = cdi.get("cost", 5)
    difficulty = cdi.get("difficulty", 5)
    invasiveness = cdi.get("invasiveness", 5)

    # 1. CDI Fit Score (0-30)
    # Penalize if scores exceed user's constraints
    cdi_fit = 30.0
    if cost > context.max_cost:
        cdi_fit -= min(15, (cost - context.max_cost) * 3)
    if difficulty > context.max_difficulty:
        cdi_fit -= min(10, (difficulty - context.max_difficulty) * 2)
    if invasiveness > context.max_invasiveness:
        cdi_fit -= min(15, (invasiveness - context.max_invasiveness) * 3)
    cdi_fit = max(0, cdi_fit)

    # 2. Use Case Match Score (0-25)
    use_case_match = 0.0
    tool_use_cases = set(tool.get("cross_references", {}).get("use_cases", []))
    user_use_cases = set(context.use_cases)
    if tool_use_cases and user_use_cases:
        overlap = len(tool_use_cases & user_use_cases)
        use_case_match = min(25, overlap * 12.5)  # 2 matches = full score

    # 3. Review Signal Score (0-20)
    review_signal = 0.0
    if matching_reviews:
        # Weight reviews from similar org types and use cases higher
        weighted_ratings = []
        for review in matching_reviews:
            weight = 1.0
            if review.get("reviewer_org_type") == context.organisation_type:
                weight += 0.5
            if review.get("use_case_tag") in context.use_cases:
                weight += 0.5
            weight += min(0.5, review.get("helpful_count", 0) * 0.1)
            weighted_ratings.append(review.get("rating", 3) * weight)

        if weighted_ratings:
            avg_weighted = sum(weighted_ratings) / len(weighted_ratings)
            # Normalize: 3-star = 10, 5-star = 20, 1-star = 0
            review_signal = max(0, min(20, (avg_weighted - 1) * 5))

    # 4. Activity Relevance Score (0-15)
    activity_relevance = 0.0
    tool_cluster = tool.get("cluster_slug", "")
    tool_slug = tool.get("slug", "")
    tool_name = tool.get("name", "").lower()
    tool_tags = [t.lower() for t in tool.get("tags", [])]

    # Boost if user browsed this cluster
    if tool_cluster in context.browsed_clusters:
        activity_relevance += 5

    # Boost if user viewed similar tools
    for viewed in context.viewed_tools:
        if viewed != tool_slug:
            viewed_tool = get_tool(viewed)
            if viewed_tool and viewed_tool.get("cluster_slug") == tool_cluster:
                activity_relevance += 2
                break

    # Boost if search queries match tool name/tags
    for query in context.searched_queries:
        query_lower = query.lower()
        if query_lower in tool_name or any(query_lower in tag for tag in tool_tags):
            activity_relevance += 5
            break

    activity_relevance = min(15, activity_relevance)

    # 5. Profile Fit Score (0-10)
    profile_fit = 5.0  # Base score

    # Country-specific considerations
    if context.country and context.data_sensitivity in ["regulated", "pii"]:
        # Prefer sovereign/local tools for regulated data
        if "sovereign-alternative" in tool.get("tags", []) or invasiveness <= 2:
            profile_fit += 3

    # Org type considerations
    if context.organisation_type == "freelance":
        # Freelancers often prefer free/cheap tools
        if cost <= 2:
            profile_fit += 2
    elif context.organisation_type in ["newsroom", "academic"]:
        # May have team needs
        if "team" in tool_name.lower() or "collaboration" in tool.get("description", "").lower():
            profile_fit += 1

    profile_fit = min(10, profile_fit)

    # Total
    total = cdi_fit + use_case_match + review_signal + activity_relevance + profile_fit

    breakdown = ScoreBreakdown(
        cdi_fit=round(cdi_fit, 1),
        use_case_match=round(use_case_match, 1),
        review_signal=round(review_signal, 1),
        activity_relevance=round(activity_relevance, 1),
        profile_fit=round(profile_fit, 1),
        total=round(total, 1),
    )

    return total, breakdown


def get_reviews_for_tool(db: Session, tool_slug: str) -> list[dict]:
    """Get reviews for a tool with reviewer context."""
    reviews = db.query(ToolReview).join(
        User, ToolReview.user_id == User.id
    ).filter(
        ToolReview.tool_slug == tool_slug,
        ToolReview.is_hidden == False
    ).all()

    result = []
    for review in reviews:
        # Count helpful votes
        helpful_count = sum(1 for v in review.votes if v.is_helpful)

        result.append({
            "rating": review.rating,
            "comment": review.comment,
            "use_case_tag": review.use_case_tag,
            "reviewer_org_type": review.user.organisation_type if review.user else None,
            "helpful_count": helpful_count,
        })

    return result


def build_explanation(
    tool: dict,
    context: UserContext,
    breakdown: ScoreBreakdown,
    reviews: list[dict],
    playbook: Optional[ToolPlaybook],
) -> tuple[str, list[Citation]]:
    """Build explanation text and citations for a recommendation.

    Explanations are personalized based on:
    - User's CDI constraints (budget, experience, data sensitivity)
    - User's saved use cases
    - User's browsing and search activity
    - Reviews from similar users

    Returns:
        Tuple of (explanation_text, citations_list)
    """
    citations = []
    explanation_parts = []

    cdi = tool.get("cdi_scores", {})
    cost = cdi.get("cost", 5)
    difficulty = cdi.get("difficulty", 5)
    invasiveness = cdi.get("invasiveness", 5)

    tool_cluster = tool.get("cluster_slug", "")
    tool_slug = tool.get("slug", "")
    tool_name = tool.get("name", "").lower()
    tool_tags = [t.lower() for t in tool.get("tags", [])]

    # 1. Activity-based explanation (most personal - put first if present)
    activity_reasons = []

    # Check if user browsed this cluster
    if tool_cluster in context.browsed_clusters:
        cluster_name = tool.get("cluster_name", tool_cluster)
        activity_reasons.append(f"You recently browsed {cluster_name} tools")

    # Check if search queries match
    for query in context.searched_queries:
        query_lower = query.lower()
        if query_lower in tool_name or any(query_lower in tag for tag in tool_tags):
            activity_reasons.append(f"Matches your search for \"{query}\"")
            break

    # Check if user viewed similar tools
    for viewed in context.viewed_tools[:5]:
        if viewed != tool_slug:
            viewed_tool = get_tool(viewed)
            if viewed_tool and viewed_tool.get("cluster_slug") == tool_cluster:
                viewed_name = viewed_tool.get("name", viewed)
                activity_reasons.append(f"Similar to {viewed_name} that you viewed")
                break

    if activity_reasons:
        explanation_parts.append(activity_reasons[0])

    # 2. Use case match explanation
    tool_use_cases = set(tool.get("cross_references", {}).get("use_cases", []))
    user_use_cases = set(context.use_cases)
    matching_use_cases = tool_use_cases & user_use_cases
    if matching_use_cases:
        uc_list = ", ".join(list(matching_use_cases)[:2])
        explanation_parts.append(f"Matches your use cases: {uc_list}")

    # 3. CDI explanation (personalized to user's constraints)
    cdi_reasons = []
    if cost <= context.max_cost:
        if cost == 0:
            cdi_reasons.append("Free to use")
        elif cost <= 2:
            cdi_reasons.append(f"Low cost ({cost}/10)")
        elif context.budget:
            cdi_reasons.append(f"Fits your {context.budget} budget")

    if difficulty <= context.max_difficulty:
        if difficulty <= 3 and context.ai_experience_level == "beginner":
            cdi_reasons.append("beginner-friendly")
        elif context.ai_experience_level == "advanced" and difficulty >= 5:
            cdi_reasons.append("advanced features for your experience level")
        elif context.ai_experience_level == "intermediate":
            cdi_reasons.append("matches your intermediate experience")

    if invasiveness <= context.max_invasiveness:
        if invasiveness == 0:
            cdi_reasons.append("runs locally - your data stays on your machine")
        elif invasiveness <= 2:
            cdi_reasons.append("minimal data exposure - good for sensitive work")
        elif context.data_sensitivity in ["regulated", "pii"]:
            cdi_reasons.append(f"data handling fits your {context.data_sensitivity} requirements")

    if cdi_reasons:
        explanation_parts.append(cdi_reasons[0])
        citations.append(Citation(
            type=CitationType.CDI_DATA,
            text=f"Cost: {cost}/10, Difficulty: {difficulty}/10, Invasiveness: {invasiveness}/10",
            source="AI Editorial Toolkit CDI Scores",
        ))

    # 4. Organization-specific insights
    if context.organisation_type:
        if context.organisation_type == "freelance" and cost <= 2:
            if "Free to use" not in explanation_parts[0] if explanation_parts else True:
                explanation_parts.append("Budget-friendly for freelancers")
        elif context.organisation_type == "newsroom" and "team" in tool.get("description", "").lower():
            explanation_parts.append("Supports team collaboration")

    # 5. Review insight
    relevant_reviews = [r for r in reviews if r.get("comment")]
    if relevant_reviews:
        # Prefer reviews from same org type
        best_review = None
        for review in relevant_reviews:
            if review.get("reviewer_org_type") == context.organisation_type:
                best_review = review
                break
        if not best_review:
            # Fall back to most helpful
            best_review = max(relevant_reviews, key=lambda r: r.get("helpful_count", 0))

        if best_review and best_review.get("comment"):
            comment = best_review["comment"]
            if len(comment) > 100:
                comment = comment[:100] + "..."

            reviewer_note = ""
            if best_review.get("reviewer_org_type") == context.organisation_type:
                reviewer_note = f" from a fellow {context.organisation_type}"

            citations.append(Citation(
                type=CitationType.REVIEW,
                text=comment,
                rating=best_review.get("rating"),
                use_case=best_review.get("use_case_tag"),
                reviewer_type=best_review.get("reviewer_org_type"),
                helpful_count=best_review.get("helpful_count", 0),
            ))

    # 6. Playbook insight
    if playbook and playbook.status == "published":
        if playbook.best_use_cases:
            explanation_parts.append(f"Best for: {playbook.best_use_cases[:80]}")
            citations.append(Citation(
                type=CitationType.PLAYBOOK,
                text=playbook.best_use_cases[:200],
                source="Tool Playbook",
            ))

    # Build final explanation
    if explanation_parts:
        explanation = ". ".join(explanation_parts[:3])  # Limit to 3 most relevant points
    else:
        # Fallback with some personalization
        fallback_parts = []
        if context.organisation_type:
            fallback_parts.append(f"Recommended for {context.organisation_type}s")
        if context.ai_experience_level:
            fallback_parts.append(f"suitable for {context.ai_experience_level} users")
        explanation = " ".join(fallback_parts) if fallback_parts else "Recommended based on your profile"

    return explanation, citations


def generate_tailored_guidance(
    tool: dict,
    context: UserContext,
    playbook: Optional[ToolPlaybook],
) -> TailoredGuidance:
    """Generate personalized training and rollout guidance.

    Args:
        tool: Tool data
        context: User context
        playbook: Optional playbook with grounded guidance

    Returns:
        TailoredGuidance with training plan and rollout approach
    """
    citations = []
    difficulty = tool.get("cdi_scores", {}).get("difficulty", 5)

    # Determine training intensity based on experience + tool difficulty
    experience = context.ai_experience_level or "intermediate"

    if experience == "beginner":
        if difficulty >= 7:
            intensity = "extended"
            duration = "2-3 weeks"
            steps = [
                "Watch introductory video tutorials",
                "Read getting started guide thoroughly",
                "Practice with sample data in sandbox mode",
                "Complete guided exercises (3-5 sessions)",
                "Pair with experienced colleague for first real task",
                "Schedule weekly check-ins for first month",
            ]
            tips = [
                "Don't rush - build confidence with small wins",
                "Keep notes on what works and what confuses you",
                "Join community forum for peer support",
            ]
        else:
            intensity = "standard"
            duration = "1 week"
            steps = [
                "Read quick-start documentation",
                "Try 2-3 practice tasks",
                "Use on a real but low-stakes project",
            ]
            tips = [
                "Start with the most basic features",
                "Bookmark the help documentation",
            ]
    elif experience == "advanced":
        intensity = "fast-track"
        duration = "1-2 days"
        steps = [
            "Skim documentation for key differentiators",
            "Review API/integration options",
            "Set up automation and shortcuts early",
            "Configure for your workflow",
        ]
        tips = [
            "Focus on advanced features that save time",
            "Consider building custom integrations",
        ]
    else:  # intermediate
        if difficulty >= 7:
            intensity = "standard"
            duration = "1-2 weeks"
            steps = [
                "Complete official tutorial",
                "Practice with sample projects",
                "Gradually integrate into workflow",
            ]
            tips = [
                "Take notes on advanced features for later",
                "Don't try to learn everything at once",
            ]
        else:
            intensity = "quick"
            duration = "2-3 days"
            steps = [
                "Review key features in documentation",
                "Try on a real project immediately",
                "Explore advanced options as needed",
            ]
            tips = ["Trust your existing AI experience"]

    training_plan = TrainingPlan(
        intensity=intensity,
        duration=duration,
        steps=steps,
        tips=tips,
    )

    # Determine rollout approach based on risk level + data sensitivity
    risk_level = context.risk_level or "medium"
    data_sensitivity = context.data_sensitivity or "internal"

    if data_sensitivity in ["regulated", "pii"] or risk_level == "low":
        pace = "cautious"
        phases = [
            {"name": "Sandbox Testing", "duration": "2-4 weeks", "description": "Test with synthetic/anonymized data only"},
            {"name": "Limited Pilot", "duration": "4-6 weeks", "description": "Small team pilot with full consent and monitoring"},
            {"name": "Gradual Rollout", "duration": "Ongoing", "description": "Expand access with clear guidelines and training"},
        ]
        gates = [
            "Legal/compliance review before pilot",
            "Data protection impact assessment",
            "Team training certification",
            "Incident response plan documented",
        ]
    elif risk_level == "high":
        pace = "fast-track"
        phases = [
            {"name": "Setup & Testing", "duration": "1 week", "description": "Configure and verify core functionality"},
            {"name": "Team Access", "duration": "1 week", "description": "Roll out to full team"},
            {"name": "Optimization", "duration": "Ongoing", "description": "Iterate based on feedback"},
        ]
        gates = ["Basic security review"]
    else:  # medium risk
        pace = "standard"
        phases = [
            {"name": "Individual Testing", "duration": "1-2 weeks", "description": "Personal evaluation and testing"},
            {"name": "Team Pilot", "duration": "2-3 weeks", "description": "Small group trial with feedback"},
            {"name": "Full Rollout", "duration": "Ongoing", "description": "Team-wide access with guidelines"},
        ]
        gates = [
            "Manager approval",
            "Basic usage guidelines documented",
        ]

    rollout_approach = RolloutApproach(
        pace=pace,
        phases=phases,
        gates=gates,
    )

    # Workflow tips
    workflow_tips = []
    if playbook and playbook.implementation_steps:
        workflow_tips.append(playbook.implementation_steps[:200])
        citations.append(Citation(
            type=CitationType.PLAYBOOK,
            text=playbook.implementation_steps[:100],
            source="Tool Playbook - Implementation Steps",
        ))

    tool_tags = tool.get("tags", [])
    if "automation" in tool_tags or "workflow" in tool.get("name", "").lower():
        workflow_tips.append("Consider automating repetitive tasks early")
    if "api" in tool.get("description", "").lower():
        workflow_tips.append("Explore API options for integration with existing tools")

    return TailoredGuidance(
        training_plan=training_plan,
        rollout_approach=rollout_approach,
        workflow_tips=workflow_tips,
        citations=citations,
    )


def get_recommendations(
    db: Session,
    user: User,
    query: Optional[str] = None,
    use_case: Optional[str] = None,
    limit: int = MAX_RECOMMENDATIONS,
    record_shown: bool = False,
) -> list[ToolRecommendation]:
    """Get personalized tool recommendations for a user with rotation.

    Recommendations rotate based on:
    - Tools recently shown are penalized to promote variety
    - User activity (searches, views, browsing) influences scores
    - Time-based diversity seed changes recommendations periodically

    Args:
        db: Database session
        user: The user to get recommendations for
        query: Optional search query to filter tools
        use_case: Optional use case/cluster slug to filter by
        limit: Maximum number of recommendations (capped at MAX_RECOMMENDATIONS)
        record_shown: Whether to record these recommendations as shown

    Returns:
        List of scored and explained recommendations
    """
    # Cap limit at MAX_RECOMMENDATIONS
    limit = min(limit, MAX_RECOMMENDATIONS)

    context = build_user_context(db, user)

    # Get recently shown tools for rotation
    recently_shown = get_recently_shown_recommendations(db, user.id)

    # Get diversity seed for this user/time period
    diversity_seed = get_diversity_seed(user.id)
    rng = random.Random(diversity_seed)

    # Get candidate tools
    if query:
        # Search by query text
        candidates = search_tools(query=query)
    elif use_case:
        # Filter by cluster slug (use_case dropdown shows clusters)
        all_tools = get_all_tools()
        candidates = [
            t for t in all_tools
            if t.get("cluster_slug") == use_case or
            use_case in t.get("cross_references", {}).get("use_cases", [])
        ]
    else:
        # All tools are candidates
        candidates = get_all_tools()

    # Exclude tools user has already reviewed (they know these)
    candidates = [t for t in candidates if t.get("slug") not in context.reviewed_tools]

    # Score each candidate
    scored = []
    for tool in candidates:
        reviews = get_reviews_for_tool(db, tool.get("slug", ""))

        # Get playbook if exists
        playbook = db.query(ToolPlaybook).filter(
            ToolPlaybook.kit_tool_slug == tool.get("slug")
        ).first()

        score, breakdown = score_tool_for_user(tool, context, reviews)

        # Apply rotation penalty for recently shown tools
        tool_slug = tool.get("slug", "")
        if tool_slug in recently_shown:
            # Penalize recently shown tools to promote rotation
            # Reduce score by 15-25 points (randomized for variety)
            penalty = 15 + rng.random() * 10
            score = max(0, score - penalty)

        # Add small diversity factor (±3 points) to create variety
        # This prevents the same exact ordering every time
        diversity_adjustment = (rng.random() - 0.5) * 6
        score = max(0, score + diversity_adjustment)

        explanation, citations = build_explanation(tool, context, breakdown, reviews, playbook)
        guidance = generate_tailored_guidance(tool, context, playbook)

        scored.append(ToolRecommendation(
            tool_slug=tool_slug,
            tool_name=tool.get("name", ""),
            cluster_slug=tool.get("cluster_slug", ""),
            cluster_name=tool.get("cluster_name", ""),
            fit_score=round(score, 1),
            score_breakdown=breakdown,
            explanation=explanation,
            citations=citations,
            cdi_scores=tool.get("cdi_scores", {}),
            tags=tool.get("tags", []),
            purpose=tool.get("purpose"),
            tailored_guidance=guidance,
        ))

    # Sort by adjusted score descending
    scored.sort(key=lambda r: r.fit_score, reverse=True)

    # Get final recommendations
    recommendations = scored[:limit]

    # Record which recommendations were shown (for future rotation)
    if record_shown and recommendations:
        shown_slugs = [r.tool_slug for r in recommendations]
        record_recommendations_shown(db, user.id, shown_slugs)

    return recommendations


def get_tool_guidance(
    db: Session,
    user: User,
    tool_slug: str,
) -> Optional[tuple[float, str, TailoredGuidance, list[Citation]]]:
    """Get personalized guidance for a specific tool.

    Args:
        db: Database session
        user: The user
        tool_slug: Tool to get guidance for

    Returns:
        Tuple of (fit_score, explanation, guidance, citations) or None
    """
    tool = get_tool(tool_slug)
    if not tool:
        return None

    context = build_user_context(db, user)
    reviews = get_reviews_for_tool(db, tool_slug)

    playbook = db.query(ToolPlaybook).filter(
        ToolPlaybook.kit_tool_slug == tool_slug
    ).first()

    score, breakdown = score_tool_for_user(tool, context, reviews)
    explanation, citations = build_explanation(tool, context, breakdown, reviews, playbook)
    guidance = generate_tailored_guidance(tool, context, playbook)

    # Add guidance citations to main list
    all_citations = citations + guidance.citations

    return score, explanation, guidance, all_citations


def get_suggested_for_location(
    db: Session,
    user: User,
    location: str,
) -> list[ToolRecommendation]:
    """Get suggested tools for a specific UI location.

    Args:
        db: Database session
        user: The user
        location: One of "home", "tool_detail", "cluster", "finder"

    Returns:
        List of recommendations appropriate for that location
    """
    limit_map = {
        "home": 3,
        "tool_detail": 2,
        "cluster": 3,
        "finder": 5,
    }
    limit = limit_map.get(location, 3)

    # For home, get general recommendations
    # For others, could be more targeted based on context
    return get_recommendations(db, user, limit=limit)
