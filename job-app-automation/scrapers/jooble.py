"""
Jooble scraper — requires a free API key from https://jooble.org/api/about
High-volume aggregator pulling from thousands of US job sites.
Uses POST request with JSON body.
"""
import requests
from typing import List, Optional

from config import JOOBLE_API_KEY
from database.models import Job
from utils.job_helpers import detect_h1b, extract_email, normalize_date, is_within_days

JOOBLE_BASE = "https://jooble.org/api"


def scrape(
    keywords: str,
    location: str,
    num_results: int = 20,
    date_filter: Optional[int] = None,
    job_type: Optional[str] = None,
) -> List[Job]:
    if not JOOBLE_API_KEY:
        raise RuntimeError("Jooble: API key not configured — add JOOBLE_API_KEY in Settings.")

    body: dict = {
        "keywords": keywords,
        "location": location or "United States",
        "page": 1,
    }
    if date_filter:
        body["SearchPeriod"] = date_filter  # days: 1, 3, 7, 30

    try:
        resp = requests.post(
            f"{JOOBLE_BASE}/{JOOBLE_API_KEY}",
            json=body,
            timeout=20,
        )
        if resp.status_code in (401, 403):
            raise RuntimeError("Jooble: Invalid API key.")
        resp.raise_for_status()
        data = resp.json()
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Jooble: {e}")

    postings = data.get("jobs", [])
    jobs: List[Job] = []

    for item in postings:
        if len(jobs) >= num_results:
            break

        date_str = normalize_date(item.get("updated"))
        if date_filter and not is_within_days(date_str, date_filter):
            continue

        type_raw = (item.get("type") or "").lower()
        if job_type and job_type.lower() not in ("any", "remote"):
            if job_type.lower() == "full-time" and type_raw and "full" not in type_raw:
                continue
            if job_type.lower() == "contract" and type_raw and "contract" not in type_raw:
                continue

        desc    = item.get("snippet", "") or ""
        sal_str = item.get("salary", "") or None
        loc     = item.get("location", location or "")

        jobs.append(Job(
            title=item.get("title", "").strip(),
            company=item.get("company", "Unknown").strip(),
            description=desc,
            link=item.get("link", ""),
            contact_email=extract_email(desc),
            source="Jooble",
            search_query=keywords,
            location=loc,
            date_posted=date_str,
            salary_text=sal_str,
            remote="remote" in (loc + desc).lower(),
            h1b_mention=detect_h1b(desc),
        ))

    return jobs
