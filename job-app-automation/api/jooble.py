"""
Jooble API client — free key required.

Jooble is one of the largest job aggregators globally, pulling from thousands
of US job sites including regional boards, company career pages, and niche
portals that JSearch and Adzuna don't always cover.

Why include it despite known redirect chains:
- The sheer volume (millions of listings) means it consistently surfaces
  roles that appear on no other board in our stack.
- The deduplicator in aggregator.py catches same-job duplicates by
  title+company fingerprint, so multi-hop redirects are the only real risk.
- Users can verify links before applying — the freshness badge will flag
  listings that are likely expired.

API docs: https://jooble.org/api/about
Get a free key: jooble.org/api/about → fill the form → receive key by email.
Add to .env as: JOOBLE_API_KEY=your_key_here
"""
from typing import List, Optional

import requests

from config import JOOBLE_API_KEY
from database.models import Job
from utils.job_helpers import detect_h1b, extract_email, normalize_date, is_within_days

_BASE_URL = "https://jooble.org/api"


def fetch(
    keywords: str,
    location: str,
    num_results: int = 20,
    date_filter: Optional[int] = None,
    job_type: Optional[str] = None,
) -> List[Job]:
    """
    Search Jooble for jobs matching keywords + location.

    Jooble uses a POST request with a JSON body. The API key is part of the URL.

    Args:
        keywords:    Job title or skill keywords.
        location:    US city/state string.
        num_results: Max jobs to return.
        date_filter: Max age in days (Jooble's SearchPeriod parameter).
        job_type:    Employment type for client-side filtering.

    Returns:
        List of Job dataclass instances.

    Raises:
        RuntimeError: If API key is missing or invalid.
    """
    if not JOOBLE_API_KEY:
        raise RuntimeError(
            "Jooble API key not configured. "
            "Add JOOBLE_API_KEY to your .env file. "
            "Get a free key at jooble.org/api/about."
        )

    body: dict = {
        "keywords": keywords,
        "location": location or "United States",
        "page":     1,
        "count":    min(num_results, 20),   # Jooble default page size is 20
    }
    if date_filter:
        # Jooble's SearchPeriod accepts number of days: 1, 3, 7, 30.
        body["SearchPeriod"] = date_filter

    try:
        response = requests.post(
            f"{_BASE_URL}/{JOOBLE_API_KEY}",
            json=body,
            timeout=20,
        )
        if response.status_code in (401, 403):
            raise RuntimeError(
                "Jooble: Invalid API key. "
                "Check JOOBLE_API_KEY in your .env file."
            )
        response.raise_for_status()
        data = response.json()
    except RuntimeError:
        raise
    except requests.ConnectionError:
        raise RuntimeError("Jooble: No internet connection.")
    except Exception as exc:
        raise RuntimeError(f"Jooble: {exc}")

    postings = data.get("jobs", [])
    jobs: List[Job] = []

    for item in postings:
        if len(jobs) >= num_results:
            break

        date_str = normalize_date(item.get("updated"))
        if date_filter and not is_within_days(date_str, date_filter):
            continue

        # Client-side job type filter using Jooble's type field.
        type_raw = (item.get("type") or "").lower()
        if job_type and job_type.lower() not in ("any", "remote"):
            if type_raw:
                jt = job_type.lower()
                if jt == "full-time" and "full" not in type_raw:
                    continue
                if jt == "contract" and "contract" not in type_raw:
                    continue

        desc    = (item.get("snippet") or "")
        loc     = (item.get("location") or location or "")
        sal_str = (item.get("salary") or None)

        jobs.append(Job(
            title         = (item.get("title") or "").strip(),
            company       = (item.get("company") or "Unknown").strip(),
            description   = desc,
            link          = item.get("link") or "",
            contact_email = extract_email(desc),
            source        = "Jooble",
            search_query  = keywords,
            location      = loc,
            date_posted   = date_str,
            salary_text   = sal_str,
            remote        = "remote" in (loc + " " + desc).lower(),
            h1b_mention   = detect_h1b(desc),
        ))

    return jobs
