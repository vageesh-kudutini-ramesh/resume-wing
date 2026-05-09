"""
RemoteOK API client — no authentication required.

RemoteOK is one of the most-visited remote job boards for tech roles.
The public JSON endpoint has been stable for years and returns fresh listings
from US and international companies that are genuinely remote-first.

Why keep this despite having JSearch:
- Zero rate limits — never throttled regardless of usage.
- Structured salary_min / salary_max fields on most listings.
- Complements JSearch with smaller companies that don't post on Google Jobs.
- Works offline from JSearch quota — critical backup when the free tier runs out.

Endpoint: https://remoteok.com/api
Auth: None — just include a descriptive User-Agent as courtesy.
"""
from typing import List, Optional

import requests

from database.models import Job
from utils.job_helpers import (
    detect_h1b, extract_email, normalize_date,
    is_within_days, salary_text,
)

_URL     = "https://remoteok.com/api"
_HEADERS = {"User-Agent": "ResumeWing/3.0 (open-source job search tool; github.com/resumewing)"}


def fetch(
    keywords: str,
    location: str = "Remote",
    num_results: int = 20,
    date_filter: Optional[int] = None,
    job_type: Optional[str] = None,
) -> List[Job]:
    """
    Fetch remote tech jobs from RemoteOK matching the given keywords.

    RemoteOK returns ALL listings in one response (~300–500 jobs).
    We filter client-side by keyword, date, and job type.

    Args:
        keywords:    Job title or skill keywords for client-side filtering.
        location:    Accepted for API compatibility; all results are remote.
        num_results: Max jobs to return after filtering.
        date_filter: Max age in days for client-side filtering.
        job_type:    Remote is the only type here; other values are ignored.

    Returns:
        List of Job dataclass instances (all remote=True).
    """
    try:
        response = requests.get(_URL, headers=_HEADERS, timeout=20)
        response.raise_for_status()
        data = response.json()
    except requests.HTTPError as exc:
        raise RuntimeError(f"RemoteOK API error (HTTP {exc.response.status_code})")
    except requests.ConnectionError:
        raise RuntimeError("RemoteOK: No internet connection.")
    except Exception as exc:
        raise RuntimeError(f"RemoteOK: {exc}")

    # First element is always a legal notice dict — skip it.
    postings = [item for item in data if isinstance(item, dict) and "id" in item]

    kw_lower = keywords.lower().strip()
    kw_parts = [k.strip() for k in kw_lower.split() if k.strip()]

    jobs: List[Job] = []
    for item in postings:
        if len(jobs) >= num_results:
            break

        title = (item.get("position") or "").strip()
        tags  = " ".join(item.get("tags") or [])
        desc  = (item.get("description") or "")
        combined = f"{title} {tags} {desc}".lower()

        # Client-side keyword filter — at least one keyword part must appear.
        if kw_parts and not any(part in combined for part in kw_parts):
            continue

        date_str = normalize_date(item.get("epoch") or item.get("date"))
        if date_filter and not is_within_days(date_str, date_filter):
            continue

        sal_min = item.get("salary_min")
        sal_max = item.get("salary_max")

        jobs.append(Job(
            title         = title,
            company       = (item.get("company") or "Unknown").strip(),
            description   = desc,
            link          = item.get("url") or f"https://remoteok.com/remote-jobs/{item.get('id', '')}",
            contact_email = extract_email(desc),
            source        = "RemoteOK",
            search_query  = keywords,
            location      = "Remote",
            date_posted   = date_str,
            salary_text   = salary_text(sal_min, sal_max, "USD"),
            salary_min    = float(sal_min) if sal_min else None,
            salary_max    = float(sal_max) if sal_max else None,
            remote        = True,
            h1b_mention   = detect_h1b(desc),
        ))

    return jobs
