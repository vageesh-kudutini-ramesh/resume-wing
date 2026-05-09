"""
USAJobs API client — Tier 2 supplemental source.

USAJobs is the official job board for the US federal government.
Links are always valid (hosted on usajobs.gov), never 404.

Why include it:
- Completely unique: no other local job tool integrates federal jobs.
- Huge differentiator for users in DC, Virginia, Maryland, and near any
  federal agency or military installation.
- Listings are well-structured with salary grade, clearance requirements,
  and explicit close dates — ideal for our expiry tracking.
- ~20,000 active listings at any time.

How to get your key (free, instant approval):
  developer.usajobs.gov/apirequest → Register → copy Authorization key.
  Your email address must be the User-Agent header value.
"""
from typing import List, Optional

import requests

from config import USAJOBS_API_KEY, USAJOBS_USER_AGENT, MAX_JOBS_PER_BOARD
from database.models import Job
from utils.job_helpers import detect_h1b, extract_email, normalize_date, salary_text

_BASE_URL = "https://data.usajobs.gov/api/search"


def fetch(
    keywords: str,
    location: str,
    num_results: int = MAX_JOBS_PER_BOARD,
    date_filter: Optional[int] = None,
    job_type: Optional[str] = None,
) -> List[Job]:
    """
    Search USAJobs for federal government positions.

    Args:
        keywords:    Job title or skill keywords.
        location:    US city/state string (e.g. "Washington, DC").
        num_results: Maximum number of Job objects to return.
        date_filter: Max age in days — mapped to DatePosted parameter.
        job_type:    Employment type — mapped to PositionSchedule.

    Returns:
        List of Job dataclass instances.

    Raises:
        RuntimeError: On missing credentials or API error.
    """
    if not (USAJOBS_API_KEY and USAJOBS_USER_AGENT):
        raise RuntimeError(
            "USAJobs credentials not configured. "
            "Add USAJOBS_API_KEY and USAJOBS_USER_AGENT (your email) to .env. "
            "Get a free key at developer.usajobs.gov/apirequest."
        )

    headers = {
        "Authorization-Key": USAJOBS_API_KEY,
        "User-Agent":        USAJOBS_USER_AGENT,
        "Host":              "data.usajobs.gov",
    }

    params: dict = {
        "Keyword":         keywords,
        "LocationName":    location,
        "ResultsPerPage":  min(num_results, 25),   # USAJobs max = 500, keep it small
        "SortField":       "OpenDate",
        "SortDirection":   "Desc",
    }
    if date_filter:
        # USAJobs DatePosted accepts a number-of-days integer.
        params["DatePosted"] = date_filter
    if job_type:
        sched = _map_job_type(job_type)
        if sched:
            params["PositionSchedule"] = sched

    try:
        response = requests.get(_BASE_URL, headers=headers, params=params, timeout=20)
        response.raise_for_status()
        search_result = response.json().get("SearchResult", {})
        items = search_result.get("SearchResultItems", [])
    except requests.HTTPError as exc:
        code = exc.response.status_code
        if code in (401, 403):
            raise RuntimeError(
                "USAJobs: Invalid credentials. "
                "Check USAJOBS_API_KEY and USAJOBS_USER_AGENT in .env."
            )
        raise RuntimeError(f"USAJobs API error (HTTP {code})")
    except requests.ConnectionError:
        raise RuntimeError("USAJobs: No internet connection.")
    except Exception as exc:
        raise RuntimeError(f"USAJobs: {exc}")

    jobs: List[Job] = []
    for item in items[:num_results]:
        job = _normalize(item, keywords, location)
        if job:
            jobs.append(job)

    return jobs


def _normalize(item: dict, keywords: str, location: str) -> Optional[Job]:
    """
    Convert a raw USAJobs SearchResultItem into a Job dataclass instance.
    Returns None if the listing lacks a title or apply URI.
    """
    descriptor = item.get("MatchedObjectDescriptor", {})

    title   = (descriptor.get("PositionTitle") or "").strip()
    uris    = descriptor.get("ApplyURI") or []
    apply_link = uris[0] if uris else ""

    if not title or not apply_link:
        return None

    # USAJobs salary comes from PositionRemuneration list.
    remuneration = descriptor.get("PositionRemuneration", [{}])[0]
    sal_min  = remuneration.get("MinimumRange")
    sal_max  = remuneration.get("MaximumRange")

    # UserArea > Details > JobSummary is the cleanest description field.
    user_area   = descriptor.get("UserArea", {})
    details     = user_area.get("Details", {})
    description = details.get("JobSummary", "") or descriptor.get("PositionTitle", "")

    org_name    = descriptor.get("OrganizationName", "US Government")
    job_location = descriptor.get("PositionLocationDisplay", location)

    # ApplicationCloseDate is an explicit expiry — use it for our expiry field.
    expires_at = descriptor.get("ApplicationCloseDate")

    return Job(
        title         = title,
        company       = org_name,
        description   = description,
        link          = apply_link,
        contact_email = None,       # Federal jobs use structured USAJobs apply
        source        = "USAJobs",
        search_query  = keywords,
        location      = job_location,
        date_posted   = normalize_date(descriptor.get("PublicationStartDate")),
        expires_at    = expires_at,
        salary_text   = salary_text(sal_min, sal_max, "USD"),
        salary_min    = float(sal_min) if sal_min else None,
        salary_max    = float(sal_max) if sal_max else None,
        remote        = "remote" in (description + job_location).lower(),
        h1b_mention   = False,      # Federal jobs don't sponsor visas
    )


def _map_job_type(job_type: str) -> Optional[str]:
    """Map our internal job_type to USAJobs PositionSchedule codes."""
    return {
        "Full-time":  "1",    # Full-Time
        "Part-time":  "2",    # Part-Time
        "Internship": "5",    # Student/Internship
    }.get(job_type)
