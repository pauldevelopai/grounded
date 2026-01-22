"""Strategy plan generation service."""
from typing import Dict, List, Any
from sqlalchemy.orm import Session
from openai import OpenAI

from app.models.toolkit import StrategyPlan
from app.services.rag import search_similar_chunks
from app.settings import settings


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
            similarity_threshold=0.6
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

    # Build prompt
    system_prompt = """You are an AI strategy consultant creating implementation plans.

CRITICAL RULES:
1. ONLY recommend tools and practices mentioned in the provided toolkit content
2. Every recommendation MUST cite the source section using [1], [2], etc.
3. Do NOT invent or suggest tools not in the toolkit
4. If toolkit doesn't cover something, acknowledge the gap
5. Be specific and actionable
6. Structure the plan clearly with sections"""

    user_prompt = f"""Create a strategic implementation plan based on these requirements:

**User Context:**
- Role: {inputs.get('role', 'Not specified')}
- Organization Type: {inputs.get('org_type', 'Not specified')}
- Risk Level: {inputs.get('risk_level', 'Not specified')}
- Data Sensitivity: {inputs.get('data_sensitivity', 'Not specified')}
- Budget: {inputs.get('budget', 'Not specified')}
- Deployment Preference: {inputs.get('deployment_pref', 'Not specified')}
- Use Cases: {', '.join(inputs.get('use_cases', [])) if inputs.get('use_cases') else 'Not specified'}

**Toolkit Content:**

{context}

**Instructions:**
Create a comprehensive strategy plan that includes:
1. Executive Summary
2. Recommended Tools (ONLY from toolkit above, cite with [1], [2], etc.)
3. Implementation Phases
4. Risk Mitigation
5. Success Metrics

Cite every recommendation using the [N] format from the toolkit content above."""

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
            "cluster": chunk.cluster,
            "tool_name": chunk.tool_name
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

Based on your requirements, we attempted to create a customized AI implementation strategy. However, the toolkit database does not currently contain sufficient content to provide grounded recommendations.

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

1. **Ingest Toolkit Content**: An administrator needs to upload relevant toolkit documentation
2. **Regenerate Plan**: Once content is available, create a new strategy plan
3. **Review Citations**: All recommendations will be grounded in verified toolkit content

## Note

This system only recommends tools and practices explicitly documented in the ingested toolkit content. This ensures all advice is traceable and verified.
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

This plan is grounded in the following toolkit content:

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

    md += f"\n*Generated by ToolkitRAG on {plan.created_at.strftime('%Y-%m-%d %H:%M UTC')}*\n"

    return md
