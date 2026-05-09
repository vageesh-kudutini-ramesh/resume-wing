"""
Remotive scraper — public REST API, no authentication required.
Endpoint: https://remotive.com/api/remote-jobs
Covers all remote job categories, many from US-based companies.
"""
import requests
from typing import List, Optional

from database.models import Job
from utils.job_helpers import detect_h1b, extract_email, normalize_date, is_within_days

REMOTIVE_URL = "https://remotive.com/api/remote-jobs"


def scrape(
    keywords: str,
    location: str,
    num_results: int = 20,
    date_filter: Optional[int] = None,
    job_type: Optional[str] = None,
) -> List[Job]:
    params = {
        "search": keywords,
        "limit": min(num_results * 3, 100),  # over-fetch for date filtering
    }

    try:
        resp = requests.get(REMOTIVE_URL, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"Remotive: {e}")

    postings = data.get("jobs", [])
    jobs: List[Job] = []

    for item in postings:
        if len(jobs) >= num_results:
            break

        date_str = normalize_date(item.get("publication_date"))
        if date_filter and not is_within_days(date_str, date_filter):
            continue

        job_type_raw = (item.get("job_type") or "").lower()
        if job_type and job_type.lower() not in ("any", "remote"):
            if job_type.lower() == "full-time" and "full" not in job_type_raw:
                continue
            if job_type.lower() == "contract" and "contract" not in job_type_raw:
                continue

        desc = item.get("description", "") or ""
        sal  = item.get("salary", "") or ""

        jobs.append(Job(
            title=item.get("title", "").strip(),
            company=item.get("company_name", "Unknown").strip(),
            description=desc,
            link=item.get("url", ""),
            contact_email=extract_email(desc),
            source="Remotive",
            search_query=keywords,
            location="Remote",
            date_posted=date_str,
            salary_text=sal if sal else None,
            remote=True,
            h1b_mention=detect_h1b(desc),
        ))

    return jobs
