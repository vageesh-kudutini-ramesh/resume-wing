"""
Jobicy scraper — public REST API, no authentication required.
Endpoint: https://jobicy.com/api/v2/remote-jobs
Aggregates remote jobs with strong US startup coverage.
"""
import requests
from typing import List, Optional

from database.models import Job
from utils.job_helpers import (
    detect_h1b, extract_email, normalize_date,
    is_within_days, salary_text,
)

JOBICY_URL = "https://jobicy.com/api/v2/remote-jobs"


def scrape(
    keywords: str,
    location: str,
    num_results: int = 20,
    date_filter: Optional[int] = None,
    job_type: Optional[str] = None,
) -> List[Job]:
    params = {
        "count": min(num_results * 2, 50),
        "geo": "usa",
    }
    if keywords:
        params["tag"] = keywords.split()[0]  # API takes single tag/keyword

    try:
        resp = requests.get(JOBICY_URL, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"Jobicy: {e}")

    postings = data.get("jobs", [])
    jobs: List[Job] = []

    for item in postings:
        if len(jobs) >= num_results:
            break

        date_str = normalize_date(item.get("pubDate"))
        if date_filter and not is_within_days(date_str, date_filter):
            continue

        job_type_raw = (item.get("jobType") or "").lower()
        if job_type and job_type.lower() not in ("any", "remote"):
            if job_type.lower() == "full-time" and "full" not in job_type_raw:
                if job_type_raw:
                    continue
            if job_type.lower() == "contract" and "contract" not in job_type_raw:
                if job_type_raw:
                    continue

        desc = item.get("jobDescription", "") or ""
        sal = salary_text(item.get("annualSalaryMin"), item.get("annualSalaryMax"), "USD")

        jobs.append(Job(
            title=item.get("jobTitle", "").strip(),
            company=item.get("companyName", "Unknown").strip(),
            description=desc,
            link=item.get("url", ""),
            contact_email=extract_email(desc),
            source="Jobicy",
            search_query=keywords,
            location=item.get("jobGeo", "Remote"),
            date_posted=date_str,
            salary_text=sal,
            remote=True,
            h1b_mention=detect_h1b(desc),
        ))

    return jobs
