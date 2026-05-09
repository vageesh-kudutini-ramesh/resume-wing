"""
Adzuna API client — Tier 1 primary source.

Adzuna is a reliable job board aggregator with a well-documented, free
developer API that has been stable for 10+ years. It covers millions of
US listings with direct employer or hosted links that don't 404.

Advantages over scraping:
- redirect_url is Adzuna-hosted and validated — not a dead external link.
- Structured salary range fields (salary_min, salary_max) in every response.
- date_posted is always present, allowing precise freshness filtering.
- Supports US state/city via the where= parameter with automatic geocoding.

Free tier: 250 requests/day.
Get both keys (app_id + app_key) at: developer.adzuna.com
"""
import re
from typing import List, Optional

import requests

from config import ADZUNA_APP_ID, ADZUNA_API_KEY, MAX_JOBS_PER_BOARD
from database.models import Job
from utils.job_helpers import detect_h1b, extract_email, normalize_date, salary_text

_BASE_URL = "https://api.adzuna.com/v1/api/jobs"

# Maps our internal date_filter (days) to Adzuna's max_days_old param.
_JOB_TYPE_PARAMS = {
    "Full-time":  {"full_time": 1},
    "Part-time":  {"part_time": 1},
    "Contract":   {"contract": 1},
    "Internship": {"contract": 1},
    "Remote":     {"what_and": "remote"},
}


def fetch(
    keywords: str,
    location: str,
    num_results: int = MAX_JOBS_PER_BOARD,
    date_filter: Optional[int] = None,
    job_type: Optional[str] = None,
) -> List[Job]:
    """
    Search Adzuna for jobs matching keywords + location.

    Args:
        keywords:    Job title or skill keywords.
        location:    US city/state or country (e.g. "New York, NY").
        num_results: Maximum number of Job objects to return.
        date_filter: Max age in days or None for any time.
        job_type:    Employment type filter or None for any.

    Returns:
        List of Job dataclass instances, sorted by date (newest first).

    Raises:
        RuntimeError: On invalid credentials or network failure.
    """
    if not (ADZUNA_APP_ID and ADZUNA_API_KEY):
        raise RuntimeError(
            "Adzuna credentials not configured. "
            "Add ADZUNA_APP_ID and ADZUNA_API_KEY to your .env file. "
            "Get free keys at developer.adzuna.com."
        )

    country  = _detect_country(location)
    per_page = min(num_results, 50)     # Adzuna max per page = 50
    jobs: List[Job] = []

    # Always enforce a freshness window.
    # If the caller didn't specify a filter we cap at 45 days — this is the
    # single most effective way to avoid Adzuna "redirect_url exists but job
    # already closed on employer's ATS" dead links.
    effective_date_filter = date_filter if date_filter else 45

    for page in range(1, 4):           # cap at 3 pages to stay within rate limits
        if len(jobs) >= num_results:
            break

        params: dict = {
            "app_id":           ADZUNA_APP_ID,
            "app_key":          ADZUNA_API_KEY,
            "results_per_page": per_page,
            "what":             keywords,
            "where":            location,
            "sort_by":          "date",           # always sort by freshness
            "content-type":     "application/json",
            "max_days_old":     effective_date_filter,
        }
        if job_type and job_type in _JOB_TYPE_PARAMS:
            params.update(_JOB_TYPE_PARAMS[job_type])

        try:
            response = requests.get(
                f"{_BASE_URL}/{country}/search/{page}",
                params=params,
                timeout=20,
            )
            response.raise_for_status()
            results = response.json().get("results", [])
        except requests.HTTPError as exc:
            code = exc.response.status_code
            if code == 401:
                raise RuntimeError(
                    "Adzuna: Invalid credentials. "
                    "Check ADZUNA_APP_ID and ADZUNA_API_KEY in your .env file."
                )
            raise RuntimeError(f"Adzuna API error (HTTP {code})")
        except requests.ConnectionError:
            raise RuntimeError("Adzuna: No internet connection.")
        except Exception as exc:
            raise RuntimeError(f"Adzuna: {exc}")

        if not results:
            break

        for item in results:
            if len(jobs) >= num_results:
                break
            job = _normalize(item, keywords, location)
            if job:
                jobs.append(job)

    return jobs


def _normalize(item: dict, keywords: str, location: str) -> Optional[Job]:
    """
    Convert a raw Adzuna API result dict into a Job dataclass instance.
    Returns None if the listing lacks a title or redirect_url.
    """
    title      = (item.get("title") or "").strip()
    apply_link = item.get("redirect_url", "")

    if not title or not apply_link:
        return None

    description = item.get("description", "")
    company     = item.get("company", {}).get("display_name", "Unknown")
    loc_data    = item.get("location", {})
    job_location = loc_data.get("display_name", location)

    sal_min  = item.get("salary_min")
    sal_max  = item.get("salary_max")
    currency = "GBP" if _detect_country(location) == "gb" else "USD"

    return Job(
        title         = title,
        company       = company,
        description   = description,
        link          = apply_link,
        contact_email = extract_email(description),
        source        = "Adzuna",
        search_query  = keywords,
        location      = job_location,
        date_posted   = normalize_date(item.get("created")),
        salary_text   = salary_text(sal_min, sal_max, currency),
        salary_min    = float(sal_min) if sal_min else None,
        salary_max    = float(sal_max) if sal_max else None,
        remote        = "remote" in (description + title).lower(),
        h1b_mention   = detect_h1b(description),
    )


def _detect_country(location: str) -> str:
    """Infer Adzuna country code from location string. Defaults to 'us'."""
    loc = location.lower()
    if any(x in loc for x in ["uk", "england", "london", "manchester", "birmingham", "glasgow"]):
        return "gb"
    if any(x in loc for x in ["canada", "toronto", "vancouver", "montreal", "calgary"]):
        return "ca"
    if any(x in loc for x in ["australia", "sydney", "melbourne", "brisbane", "perth"]):
        return "au"
    if any(x in loc for x in ["india", "bangalore", "bengaluru", "mumbai", "delhi", "hyderabad"]):
        return "in"
    if any(x in loc for x in ["germany", "berlin", "munich", "hamburg", "frankfurt"]):
        return "de"
    if any(x in loc for x in ["france", "paris", "lyon", "marseille"]):
        return "fr"
    if any(x in loc for x in ["netherlands", "amsterdam", "rotterdam"]):
        return "nl"
    if any(x in loc for x in ["singapore"]):
        return "sg"
    return "us"
