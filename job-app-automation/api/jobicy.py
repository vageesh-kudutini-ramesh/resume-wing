"""
Jobicy API client — no authentication required.

Jobicy aggregates remote jobs from US startups and tech companies.
The public API is free, stable, and returns structured salary data.

Why include it:
- Zero setup — no key, no rate limits mentioned.
- Dedicated US geo filter (geo=usa) ensures US-relevant listings.
- Salary range (annualSalaryMin / annualSalaryMax) is present on most listings.
- Good coverage of startup roles not found on larger boards.

Endpoint: https://jobicy.com/api/v2/remote-jobs
"""
from typing import List, Optional

import requests

from database.models import Job
from utils.job_helpers import (
    detect_h1b, extract_email, normalize_date,
    is_within_days, salary_text,
)

_URL = "https://jobicy.com/api/v2/remote-jobs"


def fetch(
    keywords: str,
    location: str = "Remote",
    num_results: int = 20,
    date_filter: Optional[int] = None,
    job_type: Optional[str] = None,
) -> List[Job]:
    """
    Fetch US remote jobs from Jobicy matching the given keywords.

    Args:
        keywords:    Job title or skill keywords (API supports single-tag search).
        location:    Accepted for API compatibility; all results are US remote.
        num_results: Max jobs to return.
        date_filter: Max age in days for client-side filtering.
        job_type:    Employment type for client-side filtering.

    Returns:
        List of Job dataclass instances (all remote=True).
    """
    # Jobicy's tag parameter expects a single keyword — use the first meaningful word.
    primary_keyword = keywords.split()[0] if keywords.strip() else ""

    params = {
        "count": min(num_results * 2, 50),  # fetch more to allow for filtering
        "geo":   "usa",
    }
    if primary_keyword:
        params["tag"] = primary_keyword

    try:
        response = requests.get(_URL, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
    except requests.HTTPError as exc:
        raise RuntimeError(f"Jobicy API error (HTTP {exc.response.status_code})")
    except requests.ConnectionError:
        raise RuntimeError("Jobicy: No internet connection.")
    except Exception as exc:
        raise RuntimeError(f"Jobicy: {exc}")

    postings = data.get("jobs", [])
    jobs: List[Job] = []

    for item in postings:
        if len(jobs) >= num_results:
            break

        date_str = normalize_date(item.get("pubDate"))
        if date_filter and not is_within_days(date_str, date_filter):
            continue

        # Client-side job type filter using Jobicy's jobType field.
        if job_type and job_type.lower() not in ("any", "remote"):
            job_type_raw = (item.get("jobType") or "").lower()
            if job_type_raw:
                jt = job_type.lower()
                if jt == "full-time" and "full" not in job_type_raw:
                    continue
                if jt == "contract" and "contract" not in job_type_raw:
                    continue
                if jt == "part-time" and "part" not in job_type_raw:
                    continue

        desc    = (item.get("jobDescription") or "")
        sal_min = item.get("annualSalaryMin")
        sal_max = item.get("annualSalaryMax")

        jobs.append(Job(
            title         = (item.get("jobTitle") or "").strip(),
            company       = (item.get("companyName") or "Unknown").strip(),
            description   = desc,
            link          = item.get("url") or "",
            contact_email = extract_email(desc),
            source        = "Jobicy",
            search_query  = keywords,
            location      = item.get("jobGeo") or "Remote",
            date_posted   = date_str,
            salary_text   = salary_text(sal_min, sal_max, "USD"),
            salary_min    = float(sal_min) if sal_min else None,
            salary_max    = float(sal_max) if sal_max else None,
            remote        = True,
            h1b_mention   = detect_h1b(desc),
        ))

    return jobs
