"""
RemoteOK scraper — public JSON API, no authentication required.
Endpoint: https://remoteok.com/api
Focused on remote tech jobs, many from US companies.
"""
import requests
from typing import List, Optional

from database.models import Job
from utils.job_helpers import detect_h1b, extract_email, normalize_date, is_within_days

REMOTEOK_URL = "https://remoteok.com/api"
HEADERS = {"User-Agent": "ResumeWing/2.0 (open-source job search tool)"}


def scrape(
    keywords: str,
    location: str,
    num_results: int = 20,
    date_filter: Optional[int] = None,
    job_type: Optional[str] = None,
) -> List[Job]:
    try:
        resp = requests.get(REMOTEOK_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"RemoteOK: {e}")

    # First element is a legal notice object — skip it
    postings = [item for item in data if isinstance(item, dict) and "id" in item]

    kw_lower = keywords.lower()
    jobs: List[Job] = []

    for item in postings:
        if len(jobs) >= num_results:
            break

        title    = item.get("position", "")
        tags     = " ".join(item.get("tags", []))
        desc     = item.get("description", "") or ""
        combined = f"{title} {tags} {desc}".lower()

        # Keyword filter
        if kw_lower and not any(k.strip() in combined for k in kw_lower.split()):
            continue

        # Date filter
        date_str = normalize_date(item.get("epoch") or item.get("date"))
        if date_filter and not is_within_days(date_str, date_filter):
            continue

        # Job type filter
        if job_type and job_type.lower() not in ("any", "remote"):
            continue  # RemoteOK is all-remote; skip non-remote type filters

        salary = None
        sal_min = item.get("salary_min")
        sal_max = item.get("salary_max")
        if sal_min or sal_max:
            lo = f"${int(sal_min):,}" if sal_min else ""
            hi = f"${int(sal_max):,}" if sal_max else ""
            salary = f"{lo} – {hi}/yr".strip(" –") if lo or hi else None

        jobs.append(Job(
            title=title.strip(),
            company=item.get("company", "Unknown").strip(),
            description=desc,
            link=item.get("url", f"https://remoteok.com/remote-jobs/{item.get('id','')}"),
            contact_email=extract_email(desc),
            source="RemoteOK",
            search_query=keywords,
            location="Remote",
            date_posted=date_str,
            salary_text=salary,
            remote=True,
            h1b_mention=detect_h1b(desc),
        ))

    return jobs
