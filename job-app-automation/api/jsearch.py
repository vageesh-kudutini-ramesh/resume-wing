"""
JSearch API client — Tier 1 primary source.

JSearch (by OpenWeb Ninja on RapidAPI) pulls real-time data directly from
Google for Jobs, which aggregates 50+ boards including LinkedIn, Indeed,
Glassdoor, and ZipRecruiter simultaneously.

Why this is the best source:
- Every listing includes apply_options: multiple backup apply links from
  different platforms (Workday, company careers page, LinkedIn, etc.).
  If one link dies, the user still has 3–5 fallbacks.
- Structured US city/state fields (job_city, job_state) enable precise
  geographic filtering — no guessing from free-text location strings.
- Explicit job_offer_expiration_datetime_utc field — we know exactly when
  a listing expires and can warn users before they waste time applying.
- H1B sponsorship detection via structured employer_website + description.

Free tier: 200 requests/month.
Get your key: rapidapi.com → search "JSearch" by OpenWeb Ninja → Subscribe Free
              → Your Apps → Default App → Authorization → copy X-RapidAPI-Key
"""
import json
import re
from typing import List, Optional

import requests

from config import JSEARCH_API_KEY, MAX_JOBS_PER_BOARD
from database.models import Job
from utils.job_helpers import detect_h1b, extract_email, normalize_date, salary_text

_BASE_URL = "https://jsearch.p.rapidapi.com/search"
_HEADERS = {
    "X-RapidAPI-Key":  JSEARCH_API_KEY,
    "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
}

# Maps our internal date_filter (days) to JSearch date_posted param values.
_DATE_FILTER_MAP = {
    1:  "today",
    3:  "3days",
    7:  "week",
    30: "month",
}

# Maps our internal job_type to JSearch employment_types param values.
_JOB_TYPE_MAP = {
    "Full-time":  "FULLTIME",
    "Part-time":  "PARTTIME",
    "Contract":   "CONTRACTOR",
    "Internship": "INTERN",
}


def fetch(
    keywords: str,
    location: str,
    num_results: int = MAX_JOBS_PER_BOARD,
    date_filter: Optional[int] = None,
    job_type: Optional[str] = None,
) -> List[Job]:
    """
    Search JSearch for jobs matching keywords + location.

    Args:
        keywords:    Job title or skill keywords (e.g. "Python Developer").
        location:    US city/state string (e.g. "Austin, TX") or "Remote".
        num_results: Maximum number of Job objects to return.
        date_filter: Max age in days (1, 3, 7, 30) or None for any time.
        job_type:    Employment type filter or None for any.

    Returns:
        List of Job dataclass instances, newest first.

    Raises:
        RuntimeError: On API authentication failure or network error.
    """
    if not JSEARCH_API_KEY:
        raise RuntimeError(
            "JSearch API key not configured. "
            "Add JSEARCH_API_KEY to your .env file. "
            "Get a free key at rapidapi.com → search 'JSearch'."
        )

    # JSearch query format: "keywords in location"
    query = f"{keywords} in {location}" if location and location.lower() != "remote" else keywords
    is_remote = location.lower() in ("remote", "") or not location

    params: dict = {
        "query":     query,
        "page":      "1",
        "num_pages": "1",          # one page = 10 results per request
        "country":   "us",
    }
    if is_remote:
        params["remote_jobs_only"] = "true"
    if date_filter and date_filter in _DATE_FILTER_MAP:
        params["date_posted"] = _DATE_FILTER_MAP[date_filter]
    if job_type and job_type in _JOB_TYPE_MAP:
        params["employment_types"] = _JOB_TYPE_MAP[job_type]

    jobs: List[Job] = []

    # Paginate up to ceil(num_results / 10) pages; each page = 10 results.
    pages_needed = max(1, (num_results + 9) // 10)
    for page in range(1, pages_needed + 1):
        params["page"] = str(page)
        try:
            response = requests.get(
                _BASE_URL, headers=_HEADERS, params=params, timeout=20
            )
            response.raise_for_status()
            data = response.json().get("data", [])
        except requests.HTTPError as exc:
            code = exc.response.status_code
            if code == 401 or code == 403:
                raise RuntimeError(
                    "JSearch: Invalid API key. "
                    "Check your JSEARCH_API_KEY in Settings or .env."
                )
            if code == 429:
                raise RuntimeError(
                    "JSearch: Rate limit hit. "
                    "Free tier allows 200 requests/month. "
                    "Try again later or upgrade your RapidAPI plan."
                )
            raise RuntimeError(f"JSearch API error (HTTP {code})")
        except requests.ConnectionError:
            raise RuntimeError("JSearch: No internet connection.")
        except Exception as exc:
            raise RuntimeError(f"JSearch: {exc}")

        if not data:
            break

        for item in data:
            if len(jobs) >= num_results:
                break
            job = _normalize(item, keywords, location)
            if job:
                jobs.append(job)

    return jobs


def _normalize(item: dict, keywords: str, location: str) -> Optional[Job]:
    """
    Convert a raw JSearch API result dict into a Job dataclass instance.
    Returns None if the listing lacks a title or apply link.
    """
    title   = (item.get("job_title") or "").strip()
    company = (item.get("employer_name") or "Unknown").strip()

    # Use primary apply link; fall back to first apply_option if missing.
    apply_link = item.get("job_apply_link", "")
    if not apply_link:
        options = item.get("apply_options") or []
        apply_link = options[0].get("apply_link", "") if options else ""

    if not title or not apply_link:
        return None

    description = item.get("job_description", "")
    city        = item.get("job_city", "") or ""
    state       = item.get("job_state", "") or ""
    job_location = f"{city}, {state}".strip(", ") if (city or state) else location

    # Serialize apply_options for backup link storage.
    raw_options = item.get("apply_options") or []
    apply_options_json = json.dumps([
        {"publisher": o.get("publisher", ""), "link": o.get("apply_link", "")}
        for o in raw_options
        if o.get("apply_link")
    ])

    salary_min = item.get("job_min_salary")
    salary_max = item.get("job_max_salary")
    currency   = item.get("job_salary_currency", "USD")

    return Job(
        title         = title,
        company       = company,
        description   = description,
        link          = apply_link,
        contact_email = extract_email(description),
        source        = "JSearch",
        search_query  = keywords,
        location      = job_location,
        date_posted   = normalize_date(item.get("job_posted_at_datetime_utc")),
        expires_at    = item.get("job_offer_expiration_datetime_utc"),
        salary_text   = salary_text(salary_min, salary_max, currency),
        salary_min    = float(salary_min) if salary_min else None,
        salary_max    = float(salary_max) if salary_max else None,
        remote        = bool(item.get("job_is_remote", False)),
        h1b_mention   = detect_h1b(description),
        apply_options = apply_options_json,
    )
