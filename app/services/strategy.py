"""Strategy plan generation service."""
import logging
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from openai import OpenAI

# Import auth models first to ensure User table is registered
from app.models.auth import User  # noqa: F401
from app.models.toolkit import StrategyPlan
from app.services.rag import search_similar_chunks
from app.settings import settings

logger = logging.getLogger(__name__)


async def generate_personalized_strategy_plan(
    db: Session,
    user: User,
    inputs: Dict[str, Any]
) -> StrategyPlan:
    """
    Generate a personalized strategy plan using learning profile context.

    This enhanced version uses the user's learning profile to:
    - Include their learned preferences and interests
    - Avoid tools they've dismissed
    - Emphasize tools they've favorited
    - Factor in their learning style

    Args:
        db: Database session
        user: User object (for profile access)
        inputs: Dictionary with wizard form inputs

    Returns:
        StrategyPlan object saved to database
    """
    from app.services.learning_profile import get_personalized_context

    # Get personalized context from learning profile
    try:
        personalized_context = await get_personalized_context(db, user)
    except Exception as e:
        logger.warning(f"Could not get personalized context: {e}")
        personalized_context = {}

    # Merge personalized context into inputs
    enhanced_inputs = {**inputs}
    if personalized_context:
        enhanced_inputs["learning_profile"] = personalized_context

    # Use the standard generation with enhanced inputs
    return generate_strategy_plan(db, str(user.id), enhanced_inputs)


def generate_strategy_plan(
    db: Session,
    user_id: str,
    inputs: Dict[str, Any]
) -> StrategyPlan:
    """
    Generate a grounded strategy plan based on user inputs.

    Args:
        db: Database session
        user_id: User ID creating the plan
        inputs: Dictionary with wizard form inputs:
            - role: User's role
            - org_type: Organization type
            - risk_level: Risk tolerance
            - data_sensitivity: Data sensitivity level
            - budget: Budget level
            - deployment_pref: cloud/sovereign
            - use_cases: List of use cases

    Returns:
        StrategyPlan object saved to database
    """
    # Build search queries based on inputs
    search_queries = _build_search_queries(inputs)

    # Retrieve relevant chunks from toolkit
    all_chunks = []
    for query in search_queries:
        chunks = search_similar_chunks(
            db=db,
            query=query,
            top_k=5,
            similarity_threshold=0.45
        )
        all_chunks.extend(chunks)

    # Deduplicate chunks by ID
    seen_ids = set()
    unique_chunks = []
    for chunk in all_chunks:
        if chunk.chunk_id not in seen_ids:
            seen_ids.add(chunk.chunk_id)
            unique_chunks.append(chunk)

    # If no chunks found, use fallback message
    if not unique_chunks:
        plan_text = _generate_fallback_plan(inputs)
        citations = []
    else:
        # Generate plan using LLM with retrieved context
        plan_text, citations = _generate_grounded_plan(inputs, unique_chunks)

    # Save to database
    strategy_plan = StrategyPlan(
        user_id=user_id,
        inputs=inputs,
        plan_text=plan_text,
        citations=citations
    )

    db.add(strategy_plan)
    db.commit()
    db.refresh(strategy_plan)

    return strategy_plan


def _build_search_queries(inputs: Dict[str, Any]) -> List[str]:
    """
    Build search queries based on wizard inputs.

    Returns:
        List of search query strings
    """
    queries = []

    # Base query from use cases
    use_cases = inputs.get('use_cases', [])
    if isinstance(use_cases, list) and use_cases:
        # Combine use cases into search query
        use_case_query = " ".join(use_cases)
        queries.append(f"Tools and best practices for {use_case_query}")

    # Add specific queries based on inputs
    if inputs.get('risk_level'):
        queries.append(f"Security and risk considerations for {inputs['risk_level']} risk environments")

    if inputs.get('data_sensitivity'):
        queries.append(f"Data privacy and {inputs['data_sensitivity']} data handling")

    if inputs.get('deployment_pref'):
        queries.append(f"{inputs['deployment_pref']} deployment best practices")

    if inputs.get('org_type'):
        queries.append(f"AI adoption for {inputs['org_type']} organizations")

    # Fallback general query
    if not queries:
        queries.append("AI tools and implementation best practices")

    return queries[:5]  # Limit to 5 queries


def _generate_grounded_plan(
    inputs: Dict[str, Any],
    chunks: List[Any]
) -> tuple[str, List[Dict[str, Any]]]:
    """
    Generate strategy plan using LLM with grounded context.

    Args:
        inputs: User inputs from wizard
        chunks: Retrieved toolkit chunks

    Returns:
        Tuple of (plan_text, citations)
    """
    # Build context from chunks
    context_parts = []
    for i, chunk in enumerate(chunks[:10]):  # Limit to top 10
        context_parts.append(
            f"[{i+1}] {chunk.heading or 'Section'}\n{chunk.chunk_text}"
        )

    context = "\n\n".join(context_parts)

    # Build prompt - focused on practical, actionable advice
    system_prompt = """You are a practical AI implementation advisor for journalists and newsrooms.

Your job is to create SHORT, ACTIONABLE implementation plans. Not corporate strategy documents.

RULES:
1. Be specific. Name actual tools from the provided content. No vague advice.
2. Give concrete first steps someone can do TODAY.
3. Cite sources using [1], [2] format.
4. Skip generic advice like "consider your needs" or "evaluate options."
5. If the toolkit content doesn't have a good match, say so briefly.
6. Keep sections short. Bullet points over paragraphs.
7. Focus on the 2-3 most relevant tools, not a comprehensive list.
8. If USER PERSONALIZATION is provided, tailor recommendations to their interests and learning style.
9. NEVER recommend tools the user has dismissed - they've already indicated they're not interested.
10. Give extra weight to tools the user has favorited - they've shown active interest."""

    # Build personalization section from learning profile
    personalization_section = ""
    learning_profile = inputs.get('learning_profile', {})
    if learning_profile:
        parts = []

        # Profile summary (AI-generated understanding of user)
        if learning_profile.get('profile_summary'):
            parts.append(f"User context: {learning_profile['profile_summary']}")

        # Top interests
        top_interests = learning_profile.get('top_interests', [])
        if top_interests:
            interest_names = [i['cluster'] for i in top_interests[:3]]
            parts.append(f"Key interests: {', '.join(interest_names)}")

        # Recent searches
        recent_searches = learning_profile.get('recent_searches', [])
        if recent_searches:
            parts.append(f"Recent searches: {', '.join(recent_searches[:3])}")

        # Learning style
        if learning_profile.get('learning_style'):
            parts.append(f"Learning style: {learning_profile['learning_style']}")

        # Favorited tools (emphasize these)
        favorited = learning_profile.get('favorited_tools', [])
        if favorited:
            parts.append(f"Favorited tools (user has shown interest): {', '.join(favorited[:5])}")

        # Avoided tools (exclude these from recommendations)
        avoided = learning_profile.get('avoided_tools', [])
        if avoided:
            parts.append(f"Dismissed tools (avoid recommending): {', '.join(avoided[:5])}")

        if parts:
            personalization_section = "\n\nUSER PERSONALIZATION:\n" + "\n".join(parts)

    # Build activity section if available (legacy support)
    activity_section = ""
    activity_summary = inputs.get('activity_summary')
    if activity_summary:
        searches = activity_summary.get('tool_searches', [])[:3]
        if searches:
            activity_section = f"\nRecent searches: {', '.join(searches)}"

    role = inputs.get('role', 'journalist')
    org_type = inputs.get('org_type', 'newsroom')
    use_cases = inputs.get('use_cases', [])
    use_case_text = ', '.join(use_cases) if use_cases else 'general AI adoption'

    user_prompt = f"""Based on this toolkit content, give practical recommendations for a {role} at a {org_type} who wants to: {use_case_text}
{personalization_section}
{activity_section}

TOOLKIT CONTENT:
{context}

Create a brief implementation plan with:

## Quick Start (What to do first)
One concrete action to take this week.

## Recommended Tools
List 2-3 specific tools from the content above. For each:
- Tool name and what it does
- Why it fits this use case
- CDI score if mentioned (Cost/Difficulty/Invasiveness)
- One practical tip for getting started

## Watch Out For
2-3 specific risks or gotchas based on their context:
- Risk level: {inputs.get('risk_level', 'moderate')}
- Data sensitivity: {inputs.get('data_sensitivity', 'standard')}
- Budget: {inputs.get('budget', 'limited')}

## Next Steps
3 concrete actions, numbered, that they can actually do.

Cite sources as [1], [2] etc. Keep it under 500 words total."""

    # Call OpenAI API
    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    try:
        completion = client.chat.completions.create(
            model=settings.OPENAI_CHAT_MODEL,
            temperature=0.2,  # Low for consistency
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )

        plan_text = completion.choices[0].message.content

    except Exception as e:
        raise ValueError(f"Error generating strategy plan: {e}")

    # Build citations list
    citations = []
    for chunk in chunks[:10]:
        citations.append({
            "chunk_id": chunk.chunk_id,
            "heading": chunk.heading,
            "excerpt": chunk.chunk_text[:200] + "..." if len(chunk.chunk_text) > 200 else chunk.chunk_text,
            "similarity_score": chunk.similarity_score,
            "cluster": chunk.metadata.get("cluster"),
            "tool_name": chunk.metadata.get("tool_name")
        })

    return plan_text, citations


def _generate_fallback_plan(inputs: Dict[str, Any]) -> str:
    """
    Generate fallback plan when no toolkit content is available.

    Args:
        inputs: User inputs from wizard

    Returns:
        Fallback plan text
    """
    return f"""# Strategy Plan

## Executive Summary

Based on your requirements, we attempted to create a customized AI implementation strategy. However, The AI Editorial Toolkit database does not currently contain sufficient content to provide grounded recommendations.

## Your Requirements

- **Role**: {inputs.get('role', 'Not specified')}
- **Organization**: {inputs.get('org_type', 'Not specified')}
- **Risk Level**: {inputs.get('risk_level', 'Not specified')}
- **Data Sensitivity**: {inputs.get('data_sensitivity', 'Not specified')}
- **Budget**: {inputs.get('budget', 'Not specified')}
- **Deployment**: {inputs.get('deployment_pref', 'Not specified')}
- **Use Cases**: {', '.join(inputs.get('use_cases', [])) if inputs.get('use_cases') else 'Not specified'}

## Next Steps

To receive tailored recommendations:

1. **Ingest Toolkit Content**: An administrator needs to upload relevant editorial toolkit documentation
2. **Regenerate Plan**: Once content is available, create a new strategy plan
3. **Review Citations**: All recommendations will be grounded in verified editorial toolkit content

## Note

This system only recommends tools and practices explicitly documented in the ingested AI Editorial Toolkit content. This ensures all advice is traceable and verified.
"""


def export_plan_to_markdown(plan: StrategyPlan) -> str:
    """
    Export strategy plan to Markdown format.

    Args:
        plan: StrategyPlan object

    Returns:
        Markdown formatted string
    """
    md = f"""# AI Implementation Strategy Plan

**Created**: {plan.created_at.strftime('%Y-%m-%d %H:%M UTC')}

---

## Input Parameters

- **Role**: {plan.inputs.get('role', 'Not specified')}
- **Organization Type**: {plan.inputs.get('org_type', 'Not specified')}
- **Risk Level**: {plan.inputs.get('risk_level', 'Not specified')}
- **Data Sensitivity**: {plan.inputs.get('data_sensitivity', 'Not specified')}
- **Budget**: {plan.inputs.get('budget', 'Not specified')}
- **Deployment Preference**: {plan.inputs.get('deployment_pref', 'Not specified')}
- **Use Cases**: {', '.join(plan.inputs.get('use_cases', [])) if plan.inputs.get('use_cases') else 'Not specified'}

---

## Strategy Plan

{plan.plan_text}

---

## Sources & Citations

This plan is grounded in the following AI Editorial Toolkit content:

"""

    # Add citations
    for i, citation in enumerate(plan.citations, 1):
        md += f"\n### [{i}] {citation.get('heading', 'Section')}\n\n"
        md += f"{citation.get('excerpt', '')}\n\n"

        if citation.get('tool_name'):
            md += f"**Tool**: {citation['tool_name']}\n\n"

        if citation.get('cluster'):
            md += f"**Category**: {citation['cluster']}\n\n"

        md += f"**Relevance**: {citation.get('similarity_score', 0):.2f}\n\n"
        md += "---\n"

    md += f"\n*Generated by The AI Editorial Toolkit on {plan.created_at.strftime('%Y-%m-%d %H:%M UTC')}*\n"

    return md
