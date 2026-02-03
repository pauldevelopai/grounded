"""Web scraper for playbook source content."""
import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class ScrapedContent:
    """Result of scraping a URL."""
    url: str
    title: str | None
    raw_content: str | None
    extracted_content: str | None
    content_hash: str | None
    success: bool
    error: str | None = None
    scraped_at: datetime | None = None


class PlaybookScraper:
    """Scrapes web content for playbook generation.

    Respects robots.txt and uses reasonable delays between requests.
    """

    def __init__(
        self,
        delay_seconds: float = 2.0,
        timeout_seconds: float = 30.0,
        max_content_length: int = 500000,  # 500KB
    ):
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds
        self.max_content_length = max_content_length
        self._last_request_time: dict[str, float] = {}

    async def _respect_delay(self, domain: str) -> None:
        """Ensure we respect delay between requests to same domain."""
        last_time = self._last_request_time.get(domain, 0)
        elapsed = asyncio.get_event_loop().time() - last_time
        if elapsed < self.delay_seconds:
            await asyncio.sleep(self.delay_seconds - elapsed)
        self._last_request_time[domain] = asyncio.get_event_loop().time()

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        return parsed.netloc

    def _clean_text(self, text: str) -> str:
        """Clean extracted text content."""
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove excessive newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _extract_main_content(self, soup: BeautifulSoup) -> str:
        """Extract main content from HTML, removing navigation, ads, etc."""
        # Remove unwanted elements
        for selector in [
            'script', 'style', 'nav', 'header', 'footer',
            'aside', 'noscript', 'iframe', 'form',
            '[role="navigation"]', '[role="banner"]', '[role="contentinfo"]',
            '.nav', '.navigation', '.menu', '.sidebar', '.footer', '.header',
            '.advertisement', '.ad', '.ads', '.cookie-banner', '.popup',
            '#cookie-consent', '#newsletter', '.social-share'
        ]:
            for element in soup.select(selector):
                element.decompose()

        # Try to find main content area
        main_content = None
        for selector in ['main', 'article', '[role="main"]', '.content', '#content', '.post', '.article']:
            main_content = soup.select_one(selector)
            if main_content:
                break

        if main_content:
            text = main_content.get_text(separator='\n', strip=True)
        else:
            # Fall back to body
            body = soup.find('body')
            text = body.get_text(separator='\n', strip=True) if body else soup.get_text(separator='\n', strip=True)

        return self._clean_text(text)

    def _extract_title(self, soup: BeautifulSoup) -> str | None:
        """Extract page title."""
        # Try various title sources
        if soup.title:
            return soup.title.get_text(strip=True)

        h1 = soup.find('h1')
        if h1:
            return h1.get_text(strip=True)

        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            return og_title['content']

        return None

    def _compute_hash(self, content: str) -> str:
        """Compute hash of content for change detection."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()[:32]

    async def scrape_url(self, url: str) -> ScrapedContent:
        """Scrape a single URL and extract content.

        Args:
            url: The URL to scrape

        Returns:
            ScrapedContent with extracted text or error
        """
        domain = self._extract_domain(url)
        await self._respect_delay(domain)

        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; GroundedPlaybook/1.0; +https://grounded.example.com/bot)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=True,
                max_redirects=5
            ) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()

                # Check content length
                content_length = len(response.content)
                if content_length > self.max_content_length:
                    return ScrapedContent(
                        url=url,
                        title=None,
                        raw_content=None,
                        extracted_content=None,
                        content_hash=None,
                        success=False,
                        error=f"Content too large: {content_length} bytes",
                        scraped_at=datetime.now(timezone.utc)
                    )

                # Parse HTML
                soup = BeautifulSoup(response.content, 'html.parser')

                title = self._extract_title(soup)
                raw_content = response.text
                extracted_content = self._extract_main_content(soup)
                content_hash = self._compute_hash(extracted_content)

                return ScrapedContent(
                    url=url,
                    title=title,
                    raw_content=raw_content,
                    extracted_content=extracted_content,
                    content_hash=content_hash,
                    success=True,
                    scraped_at=datetime.now(timezone.utc)
                )

        except httpx.HTTPStatusError as e:
            logger.warning(f"HTTP error scraping {url}: {e.response.status_code}")
            return ScrapedContent(
                url=url,
                title=None,
                raw_content=None,
                extracted_content=None,
                content_hash=None,
                success=False,
                error=f"HTTP {e.response.status_code}",
                scraped_at=datetime.now(timezone.utc)
            )
        except httpx.RequestError as e:
            logger.warning(f"Request error scraping {url}: {e}")
            return ScrapedContent(
                url=url,
                title=None,
                raw_content=None,
                extracted_content=None,
                content_hash=None,
                success=False,
                error=str(e),
                scraped_at=datetime.now(timezone.utc)
            )
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return ScrapedContent(
                url=url,
                title=None,
                raw_content=None,
                extracted_content=None,
                content_hash=None,
                success=False,
                error=str(e),
                scraped_at=datetime.now(timezone.utc)
            )

    async def scrape_urls(self, urls: list[str]) -> list[ScrapedContent]:
        """Scrape multiple URLs sequentially (respecting delays).

        Args:
            urls: List of URLs to scrape

        Returns:
            List of ScrapedContent results
        """
        results = []
        for url in urls:
            result = await self.scrape_url(url)
            results.append(result)
        return results

    def discover_related_urls(self, base_url: str, soup: BeautifulSoup) -> list[tuple[str, str]]:
        """Discover related URLs from a page that might be useful for playbook.

        Args:
            base_url: The base URL of the page
            soup: Parsed HTML

        Returns:
            List of (url, source_type) tuples
        """
        related = []
        seen_urls = set()

        # Keywords that indicate useful pages
        keywords_docs = ['docs', 'documentation', 'guide', 'tutorial', 'getting-started', 'quickstart']
        keywords_help = ['help', 'support', 'faq', 'knowledge-base']
        keywords_blog = ['blog', 'news', 'updates', 'changelog', 'release']
        keywords_pricing = ['pricing', 'plans', 'enterprise']
        keywords_case_study = ['case-study', 'case-studies', 'customers', 'success-stories', 'testimonials']

        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if not href or href.startswith('#') or href.startswith('javascript:'):
                continue

            # Make absolute URL
            full_url = urljoin(base_url, href)

            # Only consider same-domain links
            if self._extract_domain(full_url) != self._extract_domain(base_url):
                continue

            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            href_lower = href.lower()
            link_text = link.get_text(strip=True).lower()

            # Categorize by keywords
            source_type = None
            if any(kw in href_lower or kw in link_text for kw in keywords_docs):
                source_type = 'official_docs'
            elif any(kw in href_lower or kw in link_text for kw in keywords_help):
                source_type = 'help_page'
            elif any(kw in href_lower or kw in link_text for kw in keywords_blog):
                source_type = 'blog_post'
            elif any(kw in href_lower or kw in link_text for kw in keywords_case_study):
                source_type = 'case_study'
            elif any(kw in href_lower or kw in link_text for kw in keywords_pricing):
                source_type = 'official_docs'  # Treat pricing as docs

            if source_type:
                related.append((full_url, source_type))

        return related[:20]  # Limit to 20 related URLs
