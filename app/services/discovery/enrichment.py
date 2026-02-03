"""Tool enrichment service for generating quality descriptions.

When a tool is approved, this service fetches additional content from
the tool's website/GitHub and uses AI to generate proper descriptions.
"""
import logging
import re
from typing import Optional
import httpx
from bs4 import BeautifulSoup
from openai import OpenAI
from sqlalchemy.orm import Session

from app.models.discovery import DiscoveredTool
from app.config import settings

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None


def fetch_url_content(url: str, timeout: float = 10.0) -> Optional[str]:
    """Fetch and extract text content from a URL."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Grounded/1.0; +https://grounded.example.com)"
        }
        response = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()

        # Get text
        text = soup.get_text(separator=" ", strip=True)

        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)

        # Limit to first 8000 chars to avoid token limits
        return text[:8000] if text else None

    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None


def fetch_github_readme(github_url: str) -> Optional[str]:
    """Fetch README content from a GitHub repository."""
    try:
        # Extract owner/repo from GitHub URL
        match = re.match(r'https?://github\.com/([^/]+)/([^/]+)', github_url)
        if not match:
            return None

        owner, repo = match.groups()
        repo = repo.rstrip('.git')

        # Try to fetch README via raw.githubusercontent.com
        readme_urls = [
            f"https://raw.githubusercontent.com/{owner}/{repo}/main/README.md",
            f"https://raw.githubusercontent.com/{owner}/{repo}/master/README.md",
            f"https://raw.githubusercontent.com/{owner}/{repo}/main/readme.md",
            f"https://raw.githubusercontent.com/{owner}/{repo}/master/readme.md",
        ]

        for readme_url in readme_urls:
            try:
                response = httpx.get(readme_url, timeout=10.0)
                if response.status_code == 200:
                    content = response.text
                    # Limit to first 10000 chars
                    return content[:10000] if content else None
            except:
                continue

        return None

    except Exception as e:
        logger.warning(f"Failed to fetch GitHub README from {github_url}: {e}")
        return None


def generate_tool_content(
    tool_name: str,
    tool_url: str,
    raw_description: str,
    website_content: Optional[str] = None,
    readme_content: Optional[str] = None,
) -> dict:
    """Use AI to generate quality description and purpose for a tool.

    Returns dict with 'description', 'purpose', and 'ai_summary'.
    """
    if not client:
        logger.warning("OpenAI client not available - skipping content generation")
        return {
            "description": raw_description,
            "purpose": None,
            "ai_summary": None
        }

    # Build context from available sources
    context_parts = []

    if raw_description:
        context_parts.append(f"Original description: {raw_description}")

    if website_content:
        context_parts.append(f"Website content:\n{website_content[:4000]}")

    if readme_content:
        context_parts.append(f"GitHub README:\n{readme_content[:4000]}")

    context = "\n\n".join(context_parts)

    prompt = f"""You are a technical writer for Grounded, a journalism AI tools platform. Based on the information provided about this tool, write:

1. A clear, factual DESCRIPTION (2-3 paragraphs) explaining what the tool is and what it does. Be specific about features and capabilities. Do not make up features - only describe what you can verify from the provided content.

2. A PURPOSE statement (1-2 paragraphs) explaining why this tool is relevant for journalists and newsrooms. How could it be used in editorial workflows? What problems does it solve?

3. A brief AI_SUMMARY (1-2 sentences) that captures the essence of the tool.

Tool Name: {tool_name}
Tool URL: {tool_url}

{context}

Respond in this exact JSON format:
{{
    "description": "Your detailed description here...",
    "purpose": "Your purpose/journalism relevance statement here...",
    "ai_summary": "Brief one-line summary here..."
}}

Important:
- Be factual and accurate - do not invent features
- If information is limited, acknowledge what the tool appears to do based on available evidence
- Focus on practical value for journalists
- Use professional, clear language
- Do not include marketing fluff or exaggeration"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a technical documentation writer. Always respond with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1500,
        )

        content = response.choices[0].message.content.strip()

        # Parse JSON response
        import json

        # Try to extract JSON from response
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]

        result = json.loads(content.strip())

        return {
            "description": result.get("description", raw_description),
            "purpose": result.get("purpose"),
            "ai_summary": result.get("ai_summary"),
        }

    except Exception as e:
        logger.error(f"Failed to generate content for {tool_name}: {e}")
        return {
            "description": raw_description,
            "purpose": None,
            "ai_summary": None
        }


def enrich_tool(db: Session, tool: DiscoveredTool) -> DiscoveredTool:
    """Enrich a discovered tool with quality content.

    Fetches additional information and generates AI descriptions.
    """
    logger.info(f"Enriching tool: {tool.name}")

    # Fetch website content
    website_content = fetch_url_content(tool.url)

    # Check if it's a GitHub tool and fetch README
    readme_content = None
    github_url = None

    if "github.com" in tool.url:
        github_url = tool.url
        readme_content = fetch_github_readme(tool.url)
    elif tool.source_type == "github" and tool.source_url:
        # Source URL might be the GitHub link
        github_url = tool.source_url
        readme_content = fetch_github_readme(tool.source_url)

    # Generate quality content
    content = generate_tool_content(
        tool_name=tool.name,
        tool_url=tool.url,
        raw_description=tool.raw_description or tool.description or "",
        website_content=website_content,
        readme_content=readme_content,
    )

    # Update tool
    if content.get("description"):
        tool.description = content["description"]
    if content.get("purpose"):
        tool.purpose = content["purpose"]
    if content.get("ai_summary"):
        tool.ai_summary = content["ai_summary"]
    if github_url:
        tool.github_url = github_url

    db.commit()
    db.refresh(tool)

    logger.info(f"Tool enriched: {tool.name}")
    return tool


def enrich_tool_by_id(db: Session, tool_id: str) -> Optional[DiscoveredTool]:
    """Enrich a tool by its ID."""
    tool = db.query(DiscoveredTool).filter(DiscoveredTool.id == tool_id).first()
    if not tool:
        return None
    return enrich_tool(db, tool)
