"""Foundation content routes (glossary, ethics, CDI guide, etc.)."""
import re
from markupsafe import Markup
from typing import Optional
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse

from app.models.auth import User
from app.dependencies import get_current_user
from app.services.kit_loader import get_all_foundations, get_foundation
from app.templates_engine import templates


router = APIRouter(prefix="/foundations", tags=["foundations"])

_URL_RE = re.compile(r'(https?://\S+)')


def _linkify(text: str) -> Markup:
    """Convert URLs in text to clickable links (after HTML-escaping the rest)."""
    parts = _URL_RE.split(str(text))
    result = []
    for i, part in enumerate(parts):
        if i % 2 == 1:  # URL match
            url = part.rstrip(".,;:)")
            trailing = part[len(url):]
            result.append(
                f'<a href="{Markup.escape(url)}" target="_blank" rel="noopener" '
                f'class="text-blue-600 hover:text-blue-800 underline break-all">'
                f'{Markup.escape(url)}</a>{Markup.escape(trailing)}'
            )
        else:
            result.append(str(Markup.escape(part)))
    return Markup("".join(result))


templates.env.filters["linkify"] = _linkify


@router.get("", response_class=HTMLResponse)
async def foundations_index(
    request: Request,
    user: Optional[User] = Depends(get_current_user),
):
    """List all foundational content sections."""
    foundations = get_all_foundations()

    # Separate into main foundations and addenda
    main_sections = [f for f in foundations if not f.get("slug", "").startswith("addendum")]
    addenda = [f for f in foundations if f.get("slug", "").startswith("addendum")]

    return templates.TemplateResponse(
        "foundations/index.html",
        {
            "request": request,
            "user": user,
            "sections": main_sections,
            "addenda": addenda,
        }
    )


@router.get("/{slug}", response_class=HTMLResponse)
async def foundation_detail(
    request: Request,
    slug: str,
    user: Optional[User] = Depends(get_current_user),
):
    """Show individual foundation section."""
    section = get_foundation(slug)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    all_foundations = get_all_foundations()

    return templates.TemplateResponse(
        "foundations/detail.html",
        {
            "request": request,
            "user": user,
            "section": section,
            "all_sections": all_foundations,
        }
    )
