"""
Himalayas API client — no authentication required.

Himalayas (himalayas.app) is a curated remote job board focused on
startup and tech roles. It has a public JSON API with no key requirement.

Why include it:
- Zero setup — no key, no registration needed.
- Startup/scale-up focused: surfaces roles at companies that are growing
  fast but don't have large enough budgets to advertise on premium boards.
- Salary transparency: a large % of listings include salary ranges because
  Himalayas requires companies to disclose them.
- Clean, well-structured API response.

Endpoint: https://himalayas.app/jobs/api
"""
import html
import re
from typing import List, Optional

import requests

from database.models import Job
from utils.job_helpers import (
    detect_h1b, extract_email, normalize_date,
    is_within_days, salary_text,
)

_URL = "https://himalayas.app/jobs/api"


def fetch(
    keywords: str,
    location: str = "Remote",
    num_results: int = 20,
    date_filter: Optional[int] = None,
    job_type: Optional[str] = None,
) -> List[Job]:
    """
    Fetch remote startup jobs from Himalayas matching the given keywords.

    Himalayas supports a 'q' query parameter for keyword search.
    All results are remote by definition.

    Args:
        keywords:    Job title or skill keywords.
        location:    Accepted for API compatibility; all results are remote.
        num_results: Max jobs to return.
        date_filter: Max age in days for client-side filtering.
        job_type:    Employment type for client-side filtering.

    Returns:
        List of Job dataclass instances (all remote=True).
    """
    params: dict = {
        "limit": min(num_results * 2, 100),   # fetch extra to allow for filtering
    }
    if keywords.strip():
        params["q"] = keywords.strip()

    try:
        response = requests.get(_URL, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
    except requests.HTTPError as exc:
        raise RuntimeError(f"Himalayas API error (HTTP {exc.response.status_code})")
    except requests.ConnectionError:
        raise RuntimeError("Himalayas: No internet connection.")
    except Exception as exc:
        raise RuntimeError(f"Himalayas: {exc}")

    # Himalayas returns {"jobs": [...]} or just a list depending on API version.
    if isinstance(data, dict):
        postings = data.get("jobs", [])
    elif isinstance(data, list):
        postings = data
    else:
        return []

    jobs: List[Job] = []

    for item in postings:
        if len(jobs) >= num_results:
            break

        job = _normalize(item, keywords)
        if not job:
            continue

        if date_filter and job.date_posted:
            if not is_within_days(job.date_posted, date_filter):
                continue

        # Client-side job type filter.
        if job_type and job_type.lower() not in ("any", "remote"):
            type_raw = (item.get("jobType") or item.get("employment_type") or "").lower()
            if type_raw:
                jt = job_type.lower()
                if jt == "full-time" and "full" not in type_raw:
                    continue
                if jt == "contract" and "contract" not in type_raw:
                    continue
                if jt == "part-time" and "part" not in type_raw:
                    continue

        jobs.append(job)

    return jobs


def _normalize(item: dict, keywords: str) -> Optional[Job]:
    """
    Convert a raw Himalayas API result dict into a Job dataclass instance.
    Handles both flat and nested response formats for resilience.
    Returns None if the listing lacks a title or URL.
    """
    # Title may be at top level or nested.
    title = (
        item.get("title") or
        item.get("jobTitle") or
        item.get("position") or ""
    ).strip()

    # Apply URL may be direct or nested in refs.
    apply_link = (
        item.get("url") or
        item.get("applyUrl") or
        item.get("applicationUrl") or
        (item.get("refs") or {}).get("landing_page") or ""
    )

    if not title or not apply_link:
        return None

    # Company name may be at top level or nested.
    company_data = item.get("company") or {}
    company = (
        item.get("companyName") or
        (company_data.get("name") if isinstance(company_data, dict) else str(company_data)) or
        "Unknown"
    ).strip()

    # Description may contain HTML — strip tags for clean text.
    raw_desc = item.get("description") or item.get("content") or ""
    description = html.unescape(re.sub(r"<[^>]+>", " ", raw_desc)).strip() if raw_desc else ""

    # Salary — Himalayas usually provides structured min/max.
    sal_data = item.get("salary") or {}
    if isinstance(sal_data, dict):
        sal_min  = sal_data.get("min") or sal_data.get("minimum")
        sal_max  = sal_data.get("max") or sal_data.get("maximum")
        currency = sal_data.get("currency", "USD")
    else:
        sal_min = sal_max = None
        currency = "USD"

    # Posted date.
    date_str = normalize_date(
        item.get("publishedAt") or
        item.get("createdAt") or
        item.get("datePosted") or
        item.get("date")
    )

    return Job(
        title         = title,
        company       = company,
        description   = description,
        link          = apply_link,
        contact_email = extract_email(description),
        source        = "Himalayas",
        search_query  = keywords,
        location      = item.get("location") or "Remote",
        date_posted   = date_str,
        salary_text   = salary_text(sal_min, sal_max, currency),
        salary_min    = float(sal_min) if sal_min else None,
        salary_max    = float(sal_max) if sal_max else None,
        remote        = True,
        h1b_mention   = detect_h1b(description),
    )
