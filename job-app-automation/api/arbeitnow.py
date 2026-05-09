"""
Arbeitnow API client — no authentication required.

Arbeitnow is a tech-focused job board with strong remote coverage and a
well-maintained public REST API. Despite being European in origin, it has
a significant volume of US and international remote positions.

Why include it:
- Truly free, no key, no registration — zero friction to use.
- Structured job_types field allows reliable full-time/contract filtering.
- Paginated API means we can pull exactly the volume we need.
- Listings tend to be from smaller tech companies not covered by JSearch.

Endpoint: https://www.arbeitnow.com/api/job-board-api
"""
from typing import List, Optional

import requests

from database.models import Job
from utils.job_helpers import detect_h1b, extract_email, normalize_date, is_within_days

_URL = "https://www.arbeitnow.com/api/job-board-api"


def fetch(
    keywords: str,
    location: str,
    num_results: int = 20,
    date_filter: Optional[int] = None,
    job_type: Optional[str] = None,
) -> List[Job]:
    """
    Search Arbeitnow for tech jobs matching keywords + location.

    Location filtering is applied client-side: the API doesn't support
    structured city/state filtering, so we match against the location string.
    Remote listings are always included regardless of the location filter.

    Args:
        keywords:    Job title or skill keywords.
        location:    City/state string for client-side filtering.
        num_results: Max jobs to return.
        date_filter: Max age in days.
        job_type:    Employment type for filtering.

    Returns:
        List of Job dataclass instances.
    """
    jobs: List[Job] = []
    page = 1
    location_lower = location.lower().strip() if location else ""
    is_remote_search = location_lower in ("remote", "") or not location_lower

    while len(jobs) < num_results:
        params: dict = {"page": page}
        if keywords:
            params["search"] = keywords

        try:
            response = requests.get(_URL, params=params, timeout=20)
            response.raise_for_status()
            data = response.json()
        except requests.HTTPError as exc:
            raise RuntimeError(f"Arbeitnow API error (HTTP {exc.response.status_code})")
        except requests.ConnectionError:
            raise RuntimeError("Arbeitnow: No internet connection.")
        except Exception as exc:
            raise RuntimeError(f"Arbeitnow: {exc}")

        postings = data.get("data", [])
        if not postings:
            break

        for item in postings:
            if len(jobs) >= num_results:
                break

            # Skip non-English listings — Arbeitnow is European and includes
            # many German-language postings that are irrelevant for US job seekers.
            # The API returns a 'language' field; fall back to title heuristic.
            lang = (item.get("language") or "").lower()
            if lang and lang != "en":
                continue
            title_check = (item.get("title") or "")
            if _is_likely_non_english(title_check):
                continue

            is_remote = bool(item.get("remote", False))
            loc_raw   = (item.get("location") or "")
            loc       = "Remote" if is_remote and not loc_raw else loc_raw

            # Location filter: include if remote search, listing is remote,
            # or location string matches.
            if not is_remote_search and not is_remote:
                loc_parts = [p.strip() for p in location_lower.replace(",", " ").split() if p.strip()]
                if not any(part in loc_raw.lower() for part in loc_parts):
                    continue

            date_str = normalize_date(item.get("created_at"))
            if date_filter and not is_within_days(date_str, date_filter):
                continue

            # Job type filter using Arbeitnow's structured job_types field.
            if job_type and job_type.lower() not in ("any", "remote"):
                job_types_raw = [t.lower() for t in (item.get("job_types") or [])]
                if job_types_raw:
                    jt = job_type.lower()
                    if jt == "full-time" and not any("full" in t for t in job_types_raw):
                        continue
                    if jt == "contract" and not any("contract" in t for t in job_types_raw):
                        continue
                    if jt == "internship" and not any("intern" in t for t in job_types_raw):
                        continue

            desc = (item.get("description") or "")

            jobs.append(Job(
                title         = (item.get("title") or "").strip(),
                company       = (item.get("company_name") or "Unknown").strip(),
                description   = desc,
                link          = item.get("url") or "",
                contact_email = extract_email(desc),
                source        = "Arbeitnow",
                search_query  = keywords,
                location      = loc or location,
                date_posted   = date_str,
                remote        = is_remote,
                h1b_mention   = detect_h1b(desc),
            ))

        page += 1
        if page > 4:   # cap at 4 pages to stay respectful of the free endpoint
            break

    return jobs


def _is_likely_non_english(text: str) -> bool:
    """
    Heuristic to detect non-English (primarily German) job titles.
    Returns True if the text is likely not in English — skip these listings.
    """
    # German-specific characters are a strong signal.
    if any(ch in text for ch in "äöüÄÖÜß"):
        return True
    # Common German filler words that rarely appear in English job titles.
    german_words = {
        "und", "mit", "der", "die", "das", "für", "von", "bei",
        "als", "zur", "zum", "eine", "einen", "oder", "sind",
        "m/w/d", "w/m/d",   # German gender notation in job ads
    }
    words = set(text.lower().split())
    return bool(words & german_words)
