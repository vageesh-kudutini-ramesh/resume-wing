"""
Remotive API client — Tier 2 supplemental source (remote jobs only).

Remotive is a curated remote job board focused on tech and professional roles.
No API key is required — the public endpoint is open.

Important usage note:
  Only use this source when the user has selected "Remote" as their location
  or explicitly enabled it. Remotive exclusively lists remote positions, so
  including it in city/state searches would pollute results with irrelevant
  listings. The aggregator enforces this contract.

API docs: remotive.com/api
"""
import html
import re
from typing import List, Optional

import requests

from config import MAX_JOBS_PER_BOARD
from database.models import Job
from utils.job_helpers import detect_h1b, extract_email, normalize_date, is_within_days

_BASE_URL = "https://remotive.com/api/remote-jobs"


def fetch(
    keywords: str,
    location: str = "Remote",
    num_results: int = MAX_JOBS_PER_BOARD,
    date_filter: Optional[int] = None,
    job_type: Optional[str] = None,
) -> List[Job]:
    """
    Fetch remote jobs from Remotive matching the given keywords.

    Args:
        keywords:    Job title or skill keywords.
        location:    Accepted for API compatibility; always returns remote jobs.
        num_results: Maximum number of Job objects to return.
        date_filter: Max age in days for client-side date filtering.
        job_type:    Not supported; ignored.

    Returns:
        List of Job dataclass instances (all remote=True).
    """
    try:
        response = requests.get(
            _BASE_URL,
            params={"search": keywords, "limit": min(num_results * 2, 100)},
            timeout=15,
        )
        response.raise_for_status()
        items = response.json().get("jobs", [])
    except requests.HTTPError as exc:
        raise RuntimeError(f"Remotive API error (HTTP {exc.response.status_code})")
    except requests.ConnectionError:
        raise RuntimeError("Remotive: No internet connection.")
    except Exception as exc:
        raise RuntimeError(f"Remotive: {exc}")

    jobs: List[Job] = []
    for item in items:
        if len(jobs) >= num_results:
            break
        job = _normalize(item, keywords)
        if not job:
            continue
        # Apply date filter client-side (Remotive has no server-side date param).
        if date_filter and job.date_posted:
            if not is_within_days(job.date_posted, date_filter):
                continue
        jobs.append(job)

    return jobs


def _normalize(item: dict, keywords: str) -> Optional[Job]:
    """
    Convert a raw Remotive API result dict into a Job dataclass instance.
    Returns None if the listing lacks a title or URL.
    """
    title      = (item.get("title") or "").strip()
    apply_link = item.get("url", "")

    if not title or not apply_link:
        return None

    # Strip HTML tags — Remotive returns HTML in the description field.
    raw_desc   = item.get("description", "")
    description = html.unescape(
        re.sub(r"<[^>]+>", " ", raw_desc)
    ).strip() if raw_desc else ""

    # Remotive often has a salary field as a plain string.
    salary_raw = (item.get("salary") or "").strip() or None

    return Job(
        title         = title,
        company       = (item.get("company_name") or "Unknown").strip(),
        description   = description,
        link          = apply_link,
        contact_email = extract_email(description),
        source        = "Remotive",
        search_query  = keywords,
        location      = "Remote",
        date_posted   = normalize_date(item.get("publication_date")),
        salary_text   = salary_raw,
        remote        = True,          # Every Remotive listing is remote by definition.
        h1b_mention   = detect_h1b(description),
    )
