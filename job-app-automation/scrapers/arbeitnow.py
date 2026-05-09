"""
Arbeitnow scraper — public REST API, no authentication required.
Endpoint: https://www.arbeitnow.com/api/job-board-api
Tech-focused, remote-friendly, international with strong US presence.
"""
import requests
from typing import List, Optional

from database.models import Job
from utils.job_helpers import detect_h1b, extract_email, normalize_date, is_within_days

ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"


def scrape(
    keywords: str,
    location: str,
    num_results: int = 20,
    date_filter: Optional[int] = None,
    job_type: Optional[str] = None,
) -> List[Job]:
    jobs: List[Job] = []
    page = 1

    while len(jobs) < num_results:
        params: dict = {"page": page}
        if keywords:
            params["search"] = keywords

        try:
            resp = requests.get(ARBEITNOW_URL, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"Arbeitnow: {e}")

        postings = data.get("data", [])
        if not postings:
            break

        for item in postings:
            if len(jobs) >= num_results:
                break

            date_str = normalize_date(item.get("created_at"))
            if date_filter and not is_within_days(date_str, date_filter):
                continue

            is_remote = item.get("remote", False)
            loc = item.get("location", "") or "Remote" if is_remote else item.get("location", "")

            # Location filter — skip if location specified and not remote and no match
            if location and location.lower() not in ("remote", "remote (us only)", "remote (worldwide)"):
                loc_lower = loc.lower()
                if not any(part.strip() in loc_lower for part in location.lower().split(",")):
                    if not is_remote:
                        continue

            desc = item.get("description", "") or ""

            job_types_raw = [t.lower() for t in (item.get("job_types") or [])]
            if job_type and job_type.lower() not in ("any", "remote"):
                if job_type.lower() == "full-time" and not any("full" in t for t in job_types_raw):
                    if job_types_raw:  # only skip if we have type info
                        continue
                if job_type.lower() == "contract" and not any("contract" in t for t in job_types_raw):
                    if job_types_raw:
                        continue

            jobs.append(Job(
                title=item.get("title", "").strip(),
                company=item.get("company_name", "Unknown").strip(),
                description=desc,
                link=item.get("url", ""),
                contact_email=extract_email(desc),
                source="Arbeitnow",
                search_query=keywords,
                location=loc,
                date_posted=date_str,
                salary_text=None,
                remote=is_remote,
                h1b_mention=detect_h1b(desc),
            ))

        page += 1
        if page > 4:
            break

    return jobs
