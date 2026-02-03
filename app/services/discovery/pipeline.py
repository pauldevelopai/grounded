"""Main discovery pipeline service."""
import asyncio
import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import DiscoveredTool, DiscoveryRun, ToolMatch
from app.services.discovery.sources import DiscoverySource, RawToolData
from app.services.discovery.dedup import (
    deduplicate_tool,
    create_match_records,
    extract_domain,
    normalize_name
)

logger = logging.getLogger(__name__)


# ============================================================================
# QUALITY FILTERING CONFIGURATION
# ============================================================================

# Minimum GitHub stars required for GitHub-sourced tools
MIN_GITHUB_STARS = 50

# Journalism-relevant keywords (tools must match at least one)
JOURNALISM_KEYWORDS = [
    "journalism", "journalist", "newsroom", "news", "reporter", "editor",
    "transcription", "transcript", "verification", "fact-check", "factcheck",
    "investigation", "investigative", "source", "interview", "audio",
    "video", "media", "broadcast", "publish", "story", "article",
    "research", "data", "visualization", "chart", "graph", "map",
    "social media", "analytics", "monitoring", "archive", "scrape",
    "text-to-speech", "speech-to-text", "translation", "subtitle",
    "caption", "ai writing", "summarize", "summarization", "nlp",
    "document", "pdf", "ocr", "image", "photo", "deepfake",
]

# Spam/irrelevant keywords (auto-reject if found)
SPAM_KEYWORDS = [
    "crypto", "cryptocurrency", "nft", "blockchain", "defi",
    "casino", "gambling", "betting", "poker",
    "adult", "xxx", "porn", "nsfw",
    "mlm", "pyramid", "get rich",
    "tiktok followers", "instagram followers", "youtube subscribers",
]

# Minimum description length
MIN_DESCRIPTION_LENGTH = 50

# Minimum confidence threshold for quality pass
MIN_CONFIDENCE_THRESHOLD = 0.6


def validate_tool_quality(raw_tool: RawToolData, source_type: str) -> tuple[bool, float, dict]:
    """
    Validate tool quality based on stricter criteria.

    Args:
        raw_tool: Raw tool data from source
        source_type: Type of source (github, producthunt, etc.)

    Returns:
        Tuple of (passes_quality, adjusted_score, quality_flags)
    """
    quality_flags = {}
    score_adjustments = 0.0
    base_score = 0.5

    # Extract relevant data
    description = (raw_tool.description or "").lower()
    name = (raw_tool.name or "").lower()
    url = (raw_tool.url or "").lower()
    extra_data = raw_tool.extra_data or {}

    # 1. Check for spam keywords - auto-reject
    for spam_word in SPAM_KEYWORDS:
        if spam_word in description or spam_word in name:
            quality_flags["spam_detected"] = spam_word
            return False, 0.0, quality_flags

    # 2. GitHub stars check for GitHub sources
    if source_type == "github":
        stars = extra_data.get("stars", 0)
        if stars < MIN_GITHUB_STARS:
            quality_flags["low_github_stars"] = stars
            score_adjustments -= 0.3
        elif stars >= 100:
            score_adjustments += 0.1
        elif stars >= 500:
            score_adjustments += 0.2

    # 3. Documentation check
    has_docs = bool(raw_tool.docs_url)
    if not has_docs:
        quality_flags["no_documentation"] = True
        score_adjustments -= 0.1
    else:
        score_adjustments += 0.1

    # 4. Journalism keyword relevance
    combined_text = f"{name} {description}"
    matched_keywords = [kw for kw in JOURNALISM_KEYWORDS if kw in combined_text]
    if not matched_keywords:
        quality_flags["no_journalism_keywords"] = True
        score_adjustments -= 0.2
    else:
        quality_flags["journalism_keywords"] = matched_keywords[:5]  # Store up to 5
        score_adjustments += min(0.2, len(matched_keywords) * 0.05)

    # 5. Description quality
    desc_length = len(raw_tool.description or "")
    if desc_length < MIN_DESCRIPTION_LENGTH:
        quality_flags["short_description"] = desc_length
        score_adjustments -= 0.15
    elif desc_length >= 200:
        score_adjustments += 0.1

    # Calculate final score
    final_score = max(0.0, min(1.0, base_score + score_adjustments))

    # Determine if passes quality threshold
    passes_quality = final_score >= MIN_CONFIDENCE_THRESHOLD

    # Additional check: GitHub tools need minimum stars regardless of score
    if source_type == "github" and extra_data.get("stars", 0) < MIN_GITHUB_STARS:
        passes_quality = False

    return passes_quality, final_score, quality_flags


def calculate_journalism_relevance(raw_tool: RawToolData) -> float:
    """
    Calculate journalism relevance score for a tool.

    Returns:
        Float between 0.0 and 1.0
    """
    combined_text = f"{raw_tool.name or ''} {raw_tool.description or ''}".lower()
    matched_count = sum(1 for kw in JOURNALISM_KEYWORDS if kw in combined_text)

    # Normalize: 0-3 keywords = 0.0-0.5, 4+ keywords = 0.5-1.0
    if matched_count == 0:
        return 0.0
    elif matched_count <= 3:
        return matched_count * 0.15
    else:
        return min(1.0, 0.45 + (matched_count - 3) * 0.1)


def generate_slug(name: str, existing_slugs: set[str] | None = None) -> str:
    """
    Generate a URL-friendly slug from tool name.

    Args:
        name: Tool name
        existing_slugs: Set of existing slugs to avoid collisions

    Returns:
        Unique slug
    """
    # Convert to lowercase and replace spaces/special chars with hyphens
    slug = re.sub(r'[^\w\s-]', '', name.lower())
    slug = re.sub(r'[-\s]+', '-', slug).strip('-')

    # Ensure uniqueness if existing_slugs provided
    if existing_slugs:
        base_slug = slug
        counter = 1
        while slug in existing_slugs:
            slug = f"{base_slug}-{counter}"
            counter += 1

    return slug


def get_all_sources() -> list[DiscoverySource]:
    """Get all available discovery sources."""
    from app.services.discovery.github_source import (
        GitHubTrendingSource,
        GitHubAwesomeListSource
    )
    from app.services.discovery.producthunt_source import ProductHuntSource
    from app.services.discovery.directory_source import DirectorySource

    return [
        GitHubTrendingSource(),
        GitHubAwesomeListSource(),
        ProductHuntSource(),
        DirectorySource(),
    ]


def get_sources_by_type(source_types: list[str]) -> list[DiscoverySource]:
    """Get discovery sources filtered by type."""
    all_sources = get_all_sources()
    return [s for s in all_sources if s.source_type in source_types]


async def run_discovery_pipeline(
    db: Session,
    sources: list[str] | None = None,
    dry_run: bool = False,
    triggered_by: str = "manual",
    config: dict | None = None,
    existing_run_id: str | None = None
) -> DiscoveryRun:
    """
    Run the discovery pipeline across specified sources.

    Args:
        db: Database session
        sources: List of source types to run (None = all sources)
            Options: "github", "producthunt", "awesome_list", "directory"
        dry_run: If True, don't save to database
        triggered_by: Who triggered this run ("manual", "cron", or user ID)
        config: Optional configuration overrides:
            - steps: {"fetch": bool, "validate": bool, "dedupe": bool}
            - global_limit: int - max total items to process
            - github: {"min_stars": int, "max_results_per_topic": int}
            - producthunt: {"min_votes": int, "days_back": int}
            - awesome_list: {"max_per_list": int}
            - directory: {"max_per_directory": int}
            - custom_awesome_urls: list[str]
        existing_run_id: If provided, use existing run record instead of creating new

    Returns:
        DiscoveryRun record with stats
    """
    config = config or {}
    # Use existing run or create new one
    if existing_run_id and not dry_run:
        run = db.query(DiscoveryRun).filter(DiscoveryRun.id == existing_run_id).first()
        if not run:
            raise ValueError(f"Run not found: {existing_run_id}")
    else:
        # Create run record with progress tracking
        run_config_with_progress = (config or {}).copy()
        run_config_with_progress["progress"] = {
            "current_source": None,
            "current_source_index": 0,
            "total_sources": 0,
            "sources_completed": 0,
            "current_tool": None,
            "tools_in_current_source": 0,
            "tools_processed_in_source": 0,
        }

        run = DiscoveryRun(
            status="running",
            source_type=",".join(sources) if sources else None,
            triggered_by=triggered_by,
            run_config=run_config_with_progress
        )

        if not dry_run:
            db.add(run)
            db.commit()
            db.refresh(run)

    def update_progress(source_name=None, source_index=0, total_sources=0,
                        sources_completed=0, current_tool=None,
                        tools_in_source=0, tools_processed=0):
        """Update progress in run_config and commit."""
        if dry_run:
            return
        run.run_config = run.run_config.copy() if run.run_config else {}
        run.run_config["progress"] = {
            "current_source": source_name,
            "current_source_index": source_index,
            "total_sources": total_sources,
            "sources_completed": sources_completed,
            "current_tool": current_tool,
            "tools_in_current_source": tools_in_source,
            "tools_processed_in_source": tools_processed,
            "last_progress_at": datetime.utcnow().isoformat(),  # Track when last updated
        }
        # Also update the visible stats
        run.tools_found = tools_found
        run.tools_new = tools_new
        run.tools_updated = tools_updated
        run.tools_skipped = tools_skipped
        db.commit()

    def check_cancellation():
        """Check if the run has been cancelled by admin."""
        if dry_run:
            return False
        db.refresh(run)
        return run.status == "cancelled"

    try:
        # Get sources to run
        if sources:
            discovery_sources = get_sources_by_type(sources)
        else:
            discovery_sources = get_all_sources()

        if not discovery_sources:
            raise ValueError(f"No valid sources found for: {sources}")

        total_sources = len(discovery_sources)

        # Update initial progress
        if not dry_run:
            update_progress(
                source_name="Initializing...",
                total_sources=total_sources
            )

        # Load existing tools and slugs for deduplication
        existing_tools = db.query(DiscoveredTool).filter(
            DiscoveredTool.status != "rejected"
        ).all()
        existing_slugs = {t.slug for t in existing_tools}

        # Load kit tools for cross-reference
        kit_tools = _load_kit_tools()

        # Stats tracking
        tools_found = 0
        tools_new = 0
        tools_updated = 0
        tools_skipped = 0
        sources_completed = 0

        # Extract pipeline step configuration
        steps_config = config.get("steps", {"fetch": True, "validate": True, "dedupe": True})
        global_limit = config.get("global_limit")
        total_processed = 0

        # Run each source
        for source_index, source in enumerate(discovery_sources):
            # Check global limit
            if global_limit and total_processed >= global_limit:
                logger.info(f"Global limit reached ({global_limit}), stopping discovery")
                break

            # Check for cancellation before starting each source
            if check_cancellation():
                logger.info("Discovery run was cancelled by admin")
                run.error_message = "Cancelled by admin"
                run.completed_at = datetime.utcnow()
                if not dry_run:
                    db.commit()
                return run

            logger.info(f"Running discovery source: {source.name}")

            # Update progress: starting new source
            update_progress(
                source_name=source.name,
                source_index=source_index + 1,
                total_sources=total_sources,
                sources_completed=sources_completed,
                tools_in_source=0,
                tools_processed=0
            )

            try:
                # Build source-specific config (copy to avoid modifying original)
                source_config = dict(config.get(source.source_type, {}))

                # Handle custom awesome list URLs for awesome_list source
                if source.source_type == "awesome_list" and config.get("custom_awesome_urls"):
                    source_config["custom_urls"] = config.get("custom_awesome_urls", [])

                # Calculate remaining items if global limit is set
                if global_limit:
                    remaining = global_limit - total_processed
                    if remaining <= 0:
                        logger.info(f"Global limit reached, skipping {source.name}")
                        sources_completed += 1
                        continue

                    # Apply remaining as max limit for each source type
                    if source.source_type == "github":
                        source_config["max_results_per_topic"] = min(
                            source_config.get("max_results_per_topic", 30),
                            remaining
                        )
                    elif source.source_type == "awesome_list":
                        source_config["max_per_list"] = min(
                            source_config.get("max_per_list", 50),
                            remaining
                        )
                    elif source.source_type == "directory":
                        source_config["max_per_directory"] = min(
                            source_config.get("max_per_directory", 100),
                            remaining
                        )
                    elif source.source_type == "producthunt":
                        source_config["max_results"] = min(
                            source_config.get("max_results", 100),
                            remaining
                        )

                # Fetch tools from source (skip if fetch step disabled)
                if not steps_config.get("fetch", True):
                    logger.info(f"Skipping fetch for {source.name} (disabled)")
                    sources_completed += 1
                    continue

                raw_tools = await source.discover(source_config)
                tools_found += len(raw_tools)
                tools_in_source = len(raw_tools)

                # Update progress with tool count
                update_progress(
                    source_name=source.name,
                    source_index=source_index + 1,
                    total_sources=total_sources,
                    sources_completed=sources_completed,
                    tools_in_source=tools_in_source,
                    tools_processed=0
                )

                # Process each tool
                for tool_index, raw_tool in enumerate(raw_tools):
                    # Check global limit
                    if global_limit and total_processed >= global_limit:
                        logger.info(f"Global limit reached ({global_limit}), stopping")
                        break

                    # Check for cancellation every 10 tools
                    if tool_index > 0 and tool_index % 10 == 0:
                        if check_cancellation():
                            logger.info("Discovery run was cancelled by admin")
                            run.error_message = "Cancelled by admin"
                            run.completed_at = datetime.utcnow()
                            if not dry_run:
                                db.commit()
                            return run

                    result = process_discovered_tool(
                        db=db,
                        raw_tool=raw_tool,
                        source=source,
                        existing_tools=existing_tools,
                        existing_slugs=existing_slugs,
                        kit_tools=kit_tools,
                        dry_run=dry_run,
                        skip_validation=not steps_config.get("validate", True),
                        skip_dedupe=not steps_config.get("dedupe", True)
                    )

                    if result == "new":
                        tools_new += 1
                        total_processed += 1
                    elif result == "updated":
                        tools_updated += 1
                        total_processed += 1
                    elif result == "skipped":
                        tools_skipped += 1

                    # Update progress every 5 tools or on last tool
                    if (tool_index + 1) % 5 == 0 or tool_index == len(raw_tools) - 1:
                        update_progress(
                            source_name=source.name,
                            source_index=source_index + 1,
                            total_sources=total_sources,
                            sources_completed=sources_completed,
                            current_tool=raw_tool.name[:50] if raw_tool.name else None,
                            tools_in_source=tools_in_source,
                            tools_processed=tool_index + 1
                        )

                sources_completed += 1

            except Exception as e:
                logger.error(f"Error running source {source.name}: {e}")
                sources_completed += 1
                continue

        # Update run record - final stats
        run.status = "completed"
        run.completed_at = datetime.utcnow()
        run.tools_found = tools_found
        run.tools_new = tools_new
        run.tools_updated = tools_updated
        run.tools_skipped = tools_skipped
        # Clear progress info
        if run.run_config:
            run.run_config = {k: v for k, v in run.run_config.items() if k != "progress"}

        if not dry_run:
            db.commit()

        logger.info(
            f"Discovery completed: {tools_found} found, {tools_new} new, "
            f"{tools_updated} updated, {tools_skipped} skipped"
        )

    except Exception as e:
        logger.error(f"Discovery pipeline failed: {e}")
        run.status = "failed"
        run.error_message = str(e)
        run.completed_at = datetime.utcnow()

        if not dry_run:
            db.commit()

        raise

    return run


def process_discovered_tool(
    db: Session,
    raw_tool: RawToolData,
    source: DiscoverySource,
    existing_tools: list[DiscoveredTool],
    existing_slugs: set[str],
    kit_tools: list[dict] | None = None,
    dry_run: bool = False,
    skip_validation: bool = False,
    skip_dedupe: bool = False
) -> str:
    """
    Process a single discovered tool.

    Args:
        db: Database session
        raw_tool: Raw tool data from source
        source: The discovery source
        existing_tools: Existing discovered tools
        existing_slugs: Existing slugs for collision detection
        kit_tools: Curated kit tools for dedup
        dry_run: If True, don't save to database
        skip_validation: If True, skip quality validation step
        skip_dedupe: If True, skip deduplication check

    Returns:
        "new", "updated", or "skipped"
    """
    try:
        # Extract domain for deduplication
        url_domain = extract_domain(raw_tool.url)

        # Check if we already have this exact URL
        existing_by_url = next(
            (t for t in existing_tools
             if t.url.lower().strip().rstrip("/") == raw_tool.url.lower().strip().rstrip("/")),
            None
        )

        if existing_by_url:
            # Update last_seen_at
            if not dry_run:
                existing_by_url.last_seen_at = datetime.utcnow()
                if raw_tool.description and not existing_by_url.description:
                    existing_by_url.description = raw_tool.description
                db.commit()
            return "updated"

        # Run quality validation BEFORE deduplication (unless skipped)
        quality_score = 0.5
        quality_flags = {}
        if not skip_validation:
            passes_quality, quality_score, quality_flags = validate_tool_quality(
                raw_tool, source.source_type
            )

            if not passes_quality:
                logger.debug(
                    f"Skipping low-quality tool: {raw_tool.name} "
                    f"(score: {quality_score:.2f}, flags: {quality_flags})"
                )
                return "skipped"
        else:
            # Default score when validation is skipped
            quality_score = 0.7
            quality_flags = {"validation_skipped": True}

        # Run deduplication (unless skipped)
        matches = []
        if not skip_dedupe:
            is_duplicate, matches, dedup_confidence = deduplicate_tool(
                db=db,
                raw_tool=raw_tool,
                existing_tools=existing_tools,
                kit_tools=kit_tools
            )

            # Skip definite duplicates (exact URL or domain match)
            if is_duplicate and any(m.match_score >= 0.9 for m in matches):
                logger.debug(f"Skipping duplicate: {raw_tool.name} ({raw_tool.url})")
                return "skipped"

        # Generate unique slug
        slug = generate_slug(raw_tool.name, existing_slugs)
        existing_slugs.add(slug)

        # Use quality score as confidence (higher = better quality)
        confidence_score = quality_score

        # Calculate journalism relevance
        journalism_relevance = calculate_journalism_relevance(raw_tool)

        # Extract GitHub stars if available
        extra_data = raw_tool.extra_data or {}
        github_stars = extra_data.get("stars") if source.source_type == "github" else None

        # Determine documentation status
        has_documentation = bool(raw_tool.docs_url)

        # Create tool record with enhanced fields
        tool = DiscoveredTool(
            name=raw_tool.name,
            slug=slug,
            url=raw_tool.url,
            url_domain=url_domain,
            docs_url=raw_tool.docs_url,
            pricing_url=raw_tool.pricing_url,
            description=raw_tool.description,
            raw_description=raw_tool.description,
            categories=raw_tool.categories or [],
            tags=raw_tool.tags or [],
            source_type=source.source_type,
            source_url=raw_tool.source_url,
            source_name=source.name,
            last_updated_signal=raw_tool.last_updated,
            extra_data=extra_data,
            status="pending_review",
            confidence_score=confidence_score,
            # New quality fields
            has_documentation=has_documentation,
            github_stars=github_stars,
            journalism_relevance_score=journalism_relevance,
            quality_flags=quality_flags,
        )

        if not dry_run:
            db.add(tool)
            db.flush()  # Get the ID

            # Create match records for potential duplicates
            if matches:
                create_match_records(db, tool, matches)

            db.commit()

            # Add to existing tools for subsequent dedup checks
            existing_tools.append(tool)

        logger.info(f"Discovered new tool: {raw_tool.name} (confidence: {confidence_score:.2f})")
        return "new"

    except Exception as e:
        logger.error(f"Error processing tool {raw_tool.name}: {e}")
        db.rollback()
        return "skipped"


def _load_kit_tools() -> list[dict]:
    """Load curated kit tools for deduplication."""
    try:
        from app.services.kit_loader import load_all_tools
        tools = load_all_tools()
        return tools
    except Exception as e:
        logger.warning(f"Could not load kit tools: {e}")
        return []


async def run_single_source(
    db: Session,
    source_type: str,
    triggered_by: str = "manual",
    config: dict | None = None
) -> DiscoveryRun:
    """
    Run discovery for a single source type.

    Convenience wrapper around run_discovery_pipeline.
    """
    return await run_discovery_pipeline(
        db=db,
        sources=[source_type],
        triggered_by=triggered_by,
        config=config
    )


def get_pending_tools(db: Session, limit: int = 100, offset: int = 0) -> list[DiscoveredTool]:
    """Get tools pending review."""
    return db.query(DiscoveredTool).filter(
        DiscoveredTool.status == "pending_review"
    ).order_by(
        DiscoveredTool.confidence_score.asc(),  # Lowest confidence first (needs most review)
        DiscoveredTool.discovered_at.desc()
    ).offset(offset).limit(limit).all()


def get_tool_matches(db: Session, tool_id: str) -> list[ToolMatch]:
    """Get all potential matches for a discovered tool."""
    return db.query(ToolMatch).filter(
        ToolMatch.tool_id == tool_id,
        ToolMatch.is_duplicate.is_(None)  # Unresolved matches
    ).order_by(ToolMatch.match_score.desc()).all()


def approve_tool(
    db: Session,
    tool_id: str,
    user_id: str,
    notes: str | None = None,
    cdi_cost: int | None = None,
    cdi_difficulty: int | None = None,
    cdi_invasiveness: int | None = None,
    skip_enrichment: bool = False,
) -> DiscoveredTool:
    """
    Approve a discovered tool with optional CDI scores.

    When approved, the tool becomes immediately visible on the public /tools page.
    The tool is also enriched with AI-generated descriptions and purpose.

    Args:
        db: Database session
        tool_id: ID of tool to approve
        user_id: ID of approving user
        notes: Optional review notes
        cdi_cost: Cost score 0-10 (optional)
        cdi_difficulty: Difficulty score 0-10 (optional)
        cdi_invasiveness: Invasiveness score 0-10 (optional)
        skip_enrichment: Skip AI content generation (for testing)

    Returns:
        Approved DiscoveredTool
    """
    tool = db.query(DiscoveredTool).filter(DiscoveredTool.id == tool_id).first()
    if not tool:
        raise ValueError(f"Tool not found: {tool_id}")

    tool.status = "approved"
    tool.reviewed_by = user_id
    tool.reviewed_at = datetime.utcnow()
    tool.review_notes = notes

    # Set CDI scores if provided (validate 0-10 range)
    if cdi_cost is not None:
        tool.cdi_cost = max(0, min(10, cdi_cost))
    if cdi_difficulty is not None:
        tool.cdi_difficulty = max(0, min(10, cdi_difficulty))
    if cdi_invasiveness is not None:
        tool.cdi_invasiveness = max(0, min(10, cdi_invasiveness))

    db.commit()
    db.refresh(tool)

    # Enrich tool with AI-generated content
    if not skip_enrichment:
        try:
            from app.services.discovery.enrichment import enrich_tool
            tool = enrich_tool(db, tool)
            logger.info(f"Tool enriched with AI content: {tool.name}")
        except Exception as e:
            logger.error(f"Failed to enrich tool {tool.name}: {e}")
            # Continue without enrichment - tool is still approved

    logger.info(f"Tool approved: {tool.name} (ID: {tool_id})")
    return tool


def reject_tool(
    db: Session,
    tool_id: str,
    user_id: str,
    notes: str | None = None
) -> DiscoveredTool:
    """Reject a discovered tool."""
    tool = db.query(DiscoveredTool).filter(DiscoveredTool.id == tool_id).first()
    if not tool:
        raise ValueError(f"Tool not found: {tool_id}")

    tool.status = "rejected"
    tool.reviewed_by = user_id
    tool.reviewed_at = datetime.utcnow()
    tool.review_notes = notes

    db.commit()
    db.refresh(tool)
    return tool


def resolve_match(
    db: Session,
    match_id: str,
    is_duplicate: bool,
    user_id: str,
    notes: str | None = None
) -> ToolMatch:
    """Resolve a potential duplicate match."""
    match = db.query(ToolMatch).filter(ToolMatch.id == match_id).first()
    if not match:
        raise ValueError(f"Match not found: {match_id}")

    match.is_duplicate = is_duplicate
    match.resolved_by = user_id
    match.resolved_at = datetime.utcnow()
    match.resolution_notes = notes

    db.commit()
    db.refresh(match)
    return match
