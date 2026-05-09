"""
Findwork scraper — requires a free API key from https://findwork.dev
Specialises in tech/developer roles, strong US coverage.
"""
import requests
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from config import FINDWORK_API_KEY
from database.models import Job
from utils.job_helpers import detect_h1b, extract_email, normalize_date, is_within_days

FINDWORK_URL = "https://findwork.dev/api/jobs/"


def scrape(
    keywords: str,
    location: str,
    num_results: int = 20,
    date_filter: Optional[int] = None,
    job_type: Optional[str] = None,
) -> List[Job]:
    if not FINDWORK_API_KEY:
        raise RuntimeError("Findwork: API key not configured — add FINDWORK_API_KEY in Settings.")

    headers = {"Authorization": f"Token {FINDWORK_API_KEY}"}
    params: dict = {
        "search": keywords,
        "page_size": min(num_results, 50),
    }

    if location and location.lower() not in ("remote", "remote (us only)", "remote (worldwide)"):
        params["location"] = location
    if job_type and job_type.lower() == "remote":
        params["remote_ok"] = "true"

    if date_filter:
        cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=date_filter)).strftime("%Y-%m-%d")
        params["date_posted"] = cutoff

    try:
        resp = requests.get(FINDWORK_URL, headers=headers, params=params, timeout=20)
        if resp.status_code == 403:
            raise RuntimeError("Findwork: Invalid API key.")
        resp.raise_for_status()
        data = resp.json()
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Findwork: {e}")

    postings = data.get("results", [])
    jobs: List[Job] = []

    for item in postings:
        if len(jobs) >= num_results:
            break

        date_str = normalize_date(item.get("date"))
        if date_filter and not is_within_days(date_str, date_filter):
            continue

        emp_type = (item.get("employment_type") or "").lower()
        if job_type and job_type.lower() not in ("any", "remote"):
            if job_type.lower() == "full-time" and emp_type and "full" not in emp_type:
                continue
            if job_type.lower() == "contract" and emp_type and "contract" not in emp_type:
                continue

        desc = item.get("text", "") or ""
        is_remote = item.get("remote", False)
        loc = item.get("location", "") or ("Remote" if is_remote else "")

        jobs.append(Job(
            title=item.get("role", "").strip(),
            company=item.get("company_name", "Unknown").strip(),
            description=desc,
            link=item.get("url", ""),
            contact_email=extract_email(desc),
            source="Findwork",
            search_query=keywords,
            location=loc,
            date_posted=date_str,
            salary_text=None,
            remote=is_remote,
            h1b_mention=detect_h1b(desc),
        ))

    return jobs
