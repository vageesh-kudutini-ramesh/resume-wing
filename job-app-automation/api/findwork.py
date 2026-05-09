"""
Findwork API client — free key required.

Findwork specialises in tech and developer roles with strong US coverage.
The API is clean, well-documented, and returns high-quality listings from
companies that actively recruit engineers.

Why include it:
- Tech-only focus means less noise — nearly every listing is relevant for
  software engineers, data scientists, and DevOps roles.
- Supports remote_ok filter, date_posted cutoff, and location — all server-side.
- Free API key with no stated monthly limit for reasonable personal use.

Get your free key: https://findwork.dev  →  Register  →  copy API Token.
Add it to .env as: FINDWORK_API_KEY=your_token_here
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import requests

from config import FINDWORK_API_KEY
from database.models import Job
from utils.job_helpers import detect_h1b, extract_email, normalize_date, is_within_days

_URL = "https://findwork.dev/api/jobs/"


def fetch(
    keywords: str,
    location: str,
    num_results: int = 20,
    date_filter: Optional[int] = None,
    job_type: Optional[str] = None,
) -> List[Job]:
    """
    Search Findwork for tech jobs matching keywords + location.

    Args:
        keywords:    Job title or skill keywords.
        location:    US city/state — passed directly to server-side filter.
        num_results: Max jobs to return.
        date_filter: Max age in days — converted to date_posted cutoff.
        job_type:    Employment type (Remote sets remote_ok=true).

    Returns:
        List of Job dataclass instances.

    Raises:
        RuntimeError: If API key is missing or invalid.
    """
    if not FINDWORK_API_KEY:
        raise RuntimeError(
            "Findwork API key not configured. "
            "Add FINDWORK_API_KEY to your .env file. "
            "Get a free key at findwork.dev."
        )

    headers = {"Authorization": f"Token {FINDWORK_API_KEY}"}
    params: dict = {
        "search":    keywords,
        "page_size": min(num_results, 50),
    }

    # Pass location only if it's not a remote-only search.
    location_lower = (location or "").lower()
    is_remote_search = location_lower in ("remote", "") or not location_lower
    if not is_remote_search:
        params["location"] = location
    if job_type and job_type.lower() == "remote" or is_remote_search:
        params["remote_ok"] = "true"

    # Findwork supports a date_posted parameter as YYYY-MM-DD cutoff.
    if date_filter:
        cutoff = (
            datetime.now(tz=timezone.utc) - timedelta(days=date_filter)
        ).strftime("%Y-%m-%d")
        params["date_posted"] = cutoff

    try:
        response = requests.get(_URL, headers=headers, params=params, timeout=20)
        if response.status_code == 403:
            raise RuntimeError(
                "Findwork: Invalid API key. "
                "Check FINDWORK_API_KEY in your .env file."
            )
        response.raise_for_status()
        data = response.json()
    except RuntimeError:
        raise
    except requests.ConnectionError:
        raise RuntimeError("Findwork: No internet connection.")
    except Exception as exc:
        raise RuntimeError(f"Findwork: {exc}")

    postings = data.get("results", [])
    jobs: List[Job] = []

    for item in postings:
        if len(jobs) >= num_results:
            break

        date_str = normalize_date(item.get("date"))
        if date_filter and not is_within_days(date_str, date_filter):
            continue

        emp_type  = (item.get("employment_type") or "").lower()
        is_remote = bool(item.get("remote", False))
        loc       = (item.get("location") or "") or ("Remote" if is_remote else "")

        # Client-side job type filter for contract/full-time.
        if job_type and job_type.lower() not in ("any", "remote"):
            if emp_type:
                jt = job_type.lower()
                if jt == "full-time" and "full" not in emp_type:
                    continue
                if jt == "contract" and "contract" not in emp_type:
                    continue

        desc = (item.get("text") or "")

        jobs.append(Job(
            title         = (item.get("role") or "").strip(),
            company       = (item.get("company_name") or "Unknown").strip(),
            description   = desc,
            link          = item.get("url") or "",
            contact_email = extract_email(desc),
            source        = "Findwork",
            search_query  = keywords,
            location      = loc,
            date_posted   = date_str,
            remote        = is_remote,
            h1b_mention   = detect_h1b(desc),
        ))

    return jobs
