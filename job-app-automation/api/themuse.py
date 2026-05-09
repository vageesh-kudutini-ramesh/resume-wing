"""
The Muse API client — Tier 2 supplemental source.

The Muse is a career platform focused on tech, creative, and professional roles.
Its public API requires no authentication key — it works immediately.

Advantages:
- Zero setup: no API key, no rate limit headers.
- Strong tech/engineering job coverage.
- Each listing includes company culture data (useful for cover letters later).
- Company logos and career page links are well-maintained.

Limitations:
- ~5,000 total listings; smaller volume than JSearch or Adzuna.
- No granular city-level filtering — we filter client-side by location keyword.
- Listings can be older; always show freshness badge.

API docs: themuse.com/api/public/jobs
"""
import html
import re
from typing import List, Optional

import requests

from config import MAX_JOBS_PER_BOARD
from database.models import Job
from utils.job_helpers import detect_h1b, extract_email, normalize_date, salary_text

_BASE_URL = "https://www.themuse.com/api/public/jobs"


def fetch(
    keywords: str,
    location: str,
    num_results: int = MAX_JOBS_PER_BOARD,
    date_filter: Optional[int] = None,
    job_type: Optional[str] = None,
) -> List[Job]:
    """
    Search The Muse for jobs matching keywords, filtered client-side by location.

    Note: The Muse has no server-side location filter, so we fetch by keyword
    and filter results by location string match. This is intentional — the
    volume is small enough that client-side filtering is fast.

    Args:
        keywords:    Job title or skill keywords.
        location:    US city/state string used for client-side filtering.
        num_results: Maximum number of Job objects to return.
        date_filter: Max age in days — used to skip stale listings.
        job_type:    Not supported by The Muse API; ignored.

    Returns:
        List of Job dataclass instances.
    """
    jobs: List[Job] = []
    page = 1
    location_lower = location.lower().strip()
    is_remote = location_lower in ("remote", "") or not location_lower

    while len(jobs) < num_results:
        params = {
            "page":        page,
            "descending":  "true",   # newest first
            "category":    _map_keywords_to_category(keywords),
        }
        try:
            response = requests.get(_BASE_URL, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
        except requests.HTTPError as exc:
            raise RuntimeError(f"The Muse API error (HTTP {exc.response.status_code})")
        except requests.ConnectionError:
            raise RuntimeError("The Muse: No internet connection.")
        except Exception as exc:
            raise RuntimeError(f"The Muse: {exc}")

        results = data.get("results", [])
        if not results:
            break

        for item in results:
            if len(jobs) >= num_results:
                break

            # Client-side location filter: include if location matches or is remote search.
            job_locations = [loc.get("name", "") for loc in item.get("locations", [])]
            location_text = ", ".join(job_locations).lower()
            is_remote_listing = "remote" in location_text or not job_locations

            if not is_remote:
                # Location-specific search: skip listings that don't match.
                location_parts = [p.strip() for p in location_lower.replace(",", " ").split()]
                location_match = any(
                    any(part in location_text for part in location_parts)
                    for _ in [None]  # single iteration
                ) or is_remote_listing
                if not location_match:
                    continue

            job = _normalize(item, keywords, location)
            if job:
                # Apply date filter client-side if specified.
                if date_filter and job.date_posted:
                    from utils.job_helpers import is_within_days
                    if not is_within_days(job.date_posted, date_filter):
                        continue
                jobs.append(job)

        # The Muse paginates with ?page= starting at 1. Stop at page 5 (50 results max).
        if page >= 5 or len(results) < 10:
            break
        page += 1

    return jobs


def _normalize(item: dict, keywords: str, location: str) -> Optional[Job]:
    """
    Convert a raw Muse API result dict into a Job dataclass instance.
    Returns None if the listing lacks a title or URL.
    """
    title      = (item.get("name") or "").strip()
    apply_link = item.get("refs", {}).get("landing_page", "")

    if not title or not apply_link:
        return None

    company_data = item.get("company", {})
    company      = company_data.get("name", "Unknown")

    # Strip HTML tags from description — The Muse returns HTML content.
    raw_contents = item.get("contents", "")
    description  = html.unescape(
        re.sub(r"<[^>]+>", " ", raw_contents)
    ).strip() if raw_contents else ""

    job_locations = [loc.get("name", "") for loc in item.get("locations", [])]
    job_location  = job_locations[0] if job_locations else location

    return Job(
        title         = title,
        company       = company,
        description   = description,
        link          = apply_link,
        contact_email = extract_email(description),
        source        = "The Muse",
        search_query  = keywords,
        location      = job_location,
        date_posted   = normalize_date(item.get("publication_date")),
        remote        = any("remote" in loc.lower() for loc in job_locations),
        h1b_mention   = detect_h1b(description),
    )


def _map_keywords_to_category(keywords: str) -> str:
    """
    Map user keywords to The Muse's job category filter.
    Falls back to 'Engineering' for most tech searches.
    Muse categories: Engineering, Data and Analytics, Design and UX,
                     Product, Sales, Marketing, Customer Service, etc.
    """
    kw = keywords.lower()
    if any(t in kw for t in ["data", "analyst", "analytics", "bi ", "machine learning", "ml"]):
        return "Data and Analytics"
    if any(t in kw for t in ["design", "ux", "ui ", "user experience", "figma"]):
        return "Design and UX"
    if any(t in kw for t in ["product manager", "pm ", "product owner"]):
        return "Product"
    if any(t in kw for t in ["sales", "account executive", "business development"]):
        return "Sales"
    if any(t in kw for t in ["marketing", "seo", "content", "growth"]):
        return "Marketing"
    return "Engineering"
