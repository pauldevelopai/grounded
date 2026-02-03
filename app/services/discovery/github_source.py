"""GitHub-based discovery sources."""
import asyncio
import re
import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.services.discovery.sources import BaseDiscoverySource, RawToolData
from app.settings import settings

logger = logging.getLogger(__name__)


class GitHubTrendingSource(BaseDiscoverySource):
    """Discovers AI tools from GitHub trending and topic searches."""

    GITHUB_API_BASE = "https://api.github.com"
    AI_TOPICS = [
        "ai-tools",
        "artificial-intelligence",
        "machine-learning",
        "llm",
        "generative-ai",
        "ai",
        "chatgpt",
        "openai",
        "gpt",
        "langchain"
    ]

    def __init__(self):
        super().__init__(
            name="GitHub Trending",
            source_type="github"
        )
        self.github_token = getattr(settings, 'GITHUB_TOKEN', None)
        self.min_stars = getattr(settings, 'GITHUB_MIN_STARS', 100)

    def _get_headers(self) -> dict[str, str]:
        """Get headers for GitHub API requests."""
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        return headers

    async def discover(self, config: dict | None = None) -> list[RawToolData]:
        """
        Discover AI tools from GitHub.

        Config options:
            topics: list[str] - Topics to search (default: AI_TOPICS)
            min_stars: int - Minimum stars required (default: settings.GITHUB_MIN_STARS)
            max_results_per_topic: int - Max results per topic (default: 30)
        """
        config = config or {}
        topics = config.get("topics", self.AI_TOPICS)
        min_stars = config.get("min_stars", self.min_stars)
        max_per_topic = config.get("max_results_per_topic", 30)

        tools: list[RawToolData] = []
        seen_urls: set[str] = set()

        # Calculate date 6 months ago for recent activity filter
        six_months_ago = (datetime.utcnow() - timedelta(days=180)).strftime("%Y-%m-%d")

        async with httpx.AsyncClient(timeout=30.0) as client:
            for topic in topics:
                try:
                    topic_tools = await self._search_topic(
                        client, topic, min_stars, six_months_ago, max_per_topic
                    )
                    for tool in topic_tools:
                        if tool.url not in seen_urls:
                            seen_urls.add(tool.url)
                            tools.append(tool)

                    # Rate limit: wait between topics
                    await asyncio.sleep(1)

                except Exception as e:
                    logger.error(f"Error searching topic {topic}: {e}")
                    continue

        logger.info(f"GitHub Trending: discovered {len(tools)} tools")
        return tools

    async def _search_topic(
        self,
        client: httpx.AsyncClient,
        topic: str,
        min_stars: int,
        pushed_after: str,
        max_results: int
    ) -> list[RawToolData]:
        """Search GitHub for repositories with a specific topic."""
        tools: list[RawToolData] = []

        # Build search query
        query = f"topic:{topic} stars:>={min_stars} pushed:>={pushed_after}"

        try:
            response = await client.get(
                f"{self.GITHUB_API_BASE}/search/repositories",
                headers=self._get_headers(),
                params={
                    "q": query,
                    "sort": "stars",
                    "order": "desc",
                    "per_page": min(max_results, 100)
                }
            )
            response.raise_for_status()
            data = response.json()

            for repo in data.get("items", []):
                tool = self._repo_to_tool(repo, topic)
                if tool:
                    tools.append(tool)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.warning("GitHub API rate limit hit")
            raise

        return tools

    def _repo_to_tool(self, repo: dict[str, Any], topic: str) -> RawToolData | None:
        """Convert GitHub repo data to RawToolData."""
        try:
            name = repo.get("name", "")
            full_name = repo.get("full_name", "")

            # Use homepage if available, otherwise repo URL
            url = repo.get("homepage") or repo.get("html_url", "")
            if not url:
                return None

            # Clean up URL
            if url and not url.startswith("http"):
                url = f"https://{url}"

            description = repo.get("description", "")

            # Extract categories from topics
            repo_topics = repo.get("topics", [])
            categories = self._map_topics_to_categories(repo_topics)

            # Build extra data
            extra_data = {
                "github_repo": full_name,
                "github_url": repo.get("html_url"),
                "stars": repo.get("stargazers_count", 0),
                "forks": repo.get("forks_count", 0),
                "watchers": repo.get("watchers_count", 0),
                "language": repo.get("language"),
                "topics": repo_topics,
                "license": repo.get("license", {}).get("spdx_id") if repo.get("license") else None,
                "is_fork": repo.get("fork", False),
                "open_issues": repo.get("open_issues_count", 0),
            }

            # Get last updated from pushed_at
            pushed_at = repo.get("pushed_at", "")
            last_updated = pushed_at[:10] if pushed_at else None

            # Extract tags from description and topics
            tags = self._extract_tags(description, repo_topics)

            return RawToolData(
                name=self._clean_name(name),
                url=url,
                description=self._clean_description(description),
                source_url=repo.get("html_url", ""),
                docs_url=self._find_docs_url(repo),
                categories=categories,
                tags=tags,
                last_updated=last_updated,
                extra_data=extra_data
            )
        except Exception as e:
            logger.error(f"Error converting repo to tool: {e}")
            return None

    def _clean_name(self, name: str) -> str:
        """Clean repository name to human-readable format."""
        # Replace hyphens and underscores with spaces
        cleaned = name.replace("-", " ").replace("_", " ")
        # Capitalize words
        cleaned = " ".join(word.capitalize() for word in cleaned.split())
        return cleaned

    def _map_topics_to_categories(self, topics: list[str]) -> list[str]:
        """Map GitHub topics to standard categories."""
        category_mapping = {
            "chatbot": "Chat & Assistants",
            "chat": "Chat & Assistants",
            "assistant": "Chat & Assistants",
            "writing": "Writing & Content",
            "content-generation": "Writing & Content",
            "text-generation": "Writing & Content",
            "image-generation": "Image & Video",
            "image": "Image & Video",
            "video": "Image & Video",
            "audio": "Audio & Speech",
            "speech": "Audio & Speech",
            "text-to-speech": "Audio & Speech",
            "speech-to-text": "Audio & Speech",
            "code": "Coding & Development",
            "coding": "Coding & Development",
            "developer-tools": "Coding & Development",
            "automation": "Automation & Workflows",
            "workflow": "Automation & Workflows",
            "data-analysis": "Data & Analytics",
            "analytics": "Data & Analytics",
            "machine-learning": "Machine Learning",
            "deep-learning": "Machine Learning",
            "nlp": "Natural Language Processing",
            "natural-language-processing": "Natural Language Processing",
            "llm": "Large Language Models",
            "gpt": "Large Language Models",
            "openai": "Large Language Models",
            "langchain": "Large Language Models",
            "productivity": "Productivity",
            "research": "Research & Education",
            "education": "Research & Education",
        }

        categories = set()
        for topic in topics:
            topic_lower = topic.lower()
            if topic_lower in category_mapping:
                categories.add(category_mapping[topic_lower])

        return list(categories)

    def _find_docs_url(self, repo: dict[str, Any]) -> str | None:
        """Try to find documentation URL from repo data."""
        # Check if homepage is docs
        homepage = repo.get("homepage", "")
        if homepage and any(doc_hint in homepage.lower() for doc_hint in ["docs", "documentation", "wiki"]):
            return homepage

        # Construct potential docs URL
        full_name = repo.get("full_name", "")
        if full_name:
            # Check for common patterns
            # GitHub Pages docs
            owner, name = full_name.split("/")
            return f"https://{owner}.github.io/{name}/"

        return None


class GitHubAwesomeListSource(BaseDiscoverySource):
    """Discovers AI tools from awesome-list repositories."""

    AWESOME_LISTS = [
        ("sindresorhus/awesome", "awesome-ai"),  # Main awesome list
        ("steven2358/awesome-generative-ai", None),
        ("Hannibal046/Awesome-LLM", None),
        ("mahseema/awesome-ai-tools", None),
        ("e2b-dev/awesome-ai-agents", None),
    ]

    def __init__(self):
        super().__init__(
            name="Awesome Lists",
            source_type="awesome_list"
        )
        self.github_token = getattr(settings, 'GITHUB_TOKEN', None)

    def _get_headers(self) -> dict[str, str]:
        """Get headers for GitHub API requests."""
        headers = {
            "Accept": "application/vnd.github.raw+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        return headers

    async def discover(self, config: dict | None = None) -> list[RawToolData]:
        """
        Discover AI tools from awesome lists.

        Config options:
            lists: list[tuple[str, str|None]] - List of (repo, path) tuples
            custom_urls: list[str] - Additional GitHub repo URLs to scrape
            max_per_list: int - Max tools per list (default: no limit)
        """
        config = config or {}
        lists = list(config.get("lists", self.AWESOME_LISTS))
        max_per_list = config.get("max_per_list")

        # Parse custom URLs and add to lists
        custom_urls = config.get("custom_urls", [])
        for url in custom_urls:
            if url and "github.com" in url:
                # Extract repo from URL: https://github.com/owner/repo
                import re
                match = re.search(r'github\.com/([^/]+/[^/]+)', url.strip())
                if match:
                    repo = match.group(1).rstrip('/')
                    # Remove .git suffix if present
                    if repo.endswith('.git'):
                        repo = repo[:-4]
                    lists.append((repo, None))
                    logger.info(f"Added custom awesome list: {repo}")

        tools: list[RawToolData] = []
        seen_urls: set[str] = set()

        async with httpx.AsyncClient(timeout=30.0) as client:
            for repo, path in lists:
                try:
                    list_tools = await self._parse_awesome_list(client, repo, path)
                    added_from_list = 0
                    for tool in list_tools:
                        # Check max_per_list limit
                        if max_per_list and added_from_list >= max_per_list:
                            logger.info(f"Reached max_per_list ({max_per_list}) for {repo}")
                            break

                        if tool.url not in seen_urls:
                            seen_urls.add(tool.url)
                            tools.append(tool)
                            added_from_list += 1

                    # Rate limit
                    await asyncio.sleep(1)

                except Exception as e:
                    logger.error(f"Error parsing awesome list {repo}: {e}")
                    continue

        logger.info(f"Awesome Lists: discovered {len(tools)} tools")
        return tools

    async def _parse_awesome_list(
        self,
        client: httpx.AsyncClient,
        repo: str,
        path: str | None
    ) -> list[RawToolData]:
        """Parse a single awesome list repository."""
        tools: list[RawToolData] = []

        # Fetch README.md
        readme_path = f"{path}/README.md" if path else "README.md"
        try:
            response = await client.get(
                f"https://api.github.com/repos/{repo}/contents/{readme_path}",
                headers=self._get_headers()
            )
            response.raise_for_status()
            content = response.text

            # Parse markdown links
            tools = self._parse_markdown_links(content, repo, readme_path)

        except httpx.HTTPStatusError as e:
            logger.error(f"Error fetching {repo}/{readme_path}: {e}")

        return tools

    def _parse_markdown_links(
        self,
        content: str,
        repo: str,
        path: str
    ) -> list[RawToolData]:
        """Parse markdown content to extract tool links."""
        tools: list[RawToolData] = []

        # Pattern to match: - [Name](url) - Description
        # Also matches: * [Name](url) - Description
        link_pattern = re.compile(
            r'^[\s]*[-*]\s*\[([^\]]+)\]\(([^)]+)\)\s*[-–:]*\s*(.*)$',
            re.MULTILINE
        )

        current_category = "General"

        # Also track headers for categorization
        header_pattern = re.compile(r'^#+\s*(.+)$', re.MULTILINE)
        headers = list(header_pattern.finditer(content))
        header_positions = [(m.start(), m.group(1).strip()) for m in headers]

        for match in link_pattern.finditer(content):
            name = match.group(1).strip()
            url = match.group(2).strip()
            description = match.group(3).strip()

            # Skip invalid URLs
            if not url.startswith("http"):
                continue

            # Skip internal/relative links
            if url.startswith("#") or "github.com" in url and "/blob/" in url:
                continue

            # Skip common non-tool links
            skip_patterns = ["badge", "shield", "license", "contributing", "awesome.re"]
            if any(pattern in url.lower() for pattern in skip_patterns):
                continue

            # Find current category based on position
            match_pos = match.start()
            for header_pos, header_text in reversed(header_positions):
                if header_pos < match_pos:
                    current_category = header_text
                    break

            # Build source URL (line in awesome list)
            source_url = f"https://github.com/{repo}/blob/main/{path}"

            # Extract tags
            tags = self._extract_tags(
                f"{name} {description}",
                [current_category]
            )

            tools.append(RawToolData(
                name=name,
                url=url,
                description=self._clean_description(description),
                source_url=source_url,
                categories=[current_category] if current_category != "General" else [],
                tags=tags,
                extra_data={
                    "awesome_list": repo,
                    "section": current_category
                }
            ))

        return tools
