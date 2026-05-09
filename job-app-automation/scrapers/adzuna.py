"""
Adzuna API scraper — most reliable source.
Official free API with date-posted and job-type filter support.
"""
import re
import requests
from typing import List, Optional

from config import ADZUNA_APP_ID, ADZUNA_API_KEY, MAX_JOBS_PER_BOARD
from database.models import Job

ADZUNA_BASE = "https://api.adzuna.com/v1/api/jobs"

JOB_TYPE_PARAMS = {
    "Full-time":  {"full_time": 1},
    "Part-time":  {"part_time": 1},
    "Contract":   {"contract": 1},
    "Internship": {"contract": 1},
    "Remote":     {"what_and": "remote"},
}


def scrape(
    keywords: str,
    location: str,
    num_results: int = MAX_JOBS_PER_BOARD,
    date_filter: Optional[int] = None,
    job_type: Optional[str] = None,
) -> List[Job]:
    country  = _detect_country(location)
    per_page = min(num_results, 50)
    jobs: List[Job] = []
    page = 1

    while len(jobs) < num_results:
        try:
            params = {
                "app_id":           ADZUNA_APP_ID,
                "app_key":          ADZUNA_API_KEY,
                "results_per_page": per_page,
                "what":             keywords,
                "where":            location,
                "sort_by":          "relevance",
                "content-type":     "application/json",
            }
            if date_filter:
                params["max_days_old"] = date_filter
            if job_type and job_type in JOB_TYPE_PARAMS:
                params.update(JOB_TYPE_PARAMS[job_type])

            resp = requests.get(
                f"{ADZUNA_BASE}/{country}/search/{page}",
                params=params,
                timeout=20,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if not results:
                break

            for item in results:
                if len(jobs) >= num_results:
                    break
                desc = item.get("description", "")
                jobs.append(Job(
                    title=item.get("title", "").strip(),
                    company=item.get("company", {}).get("display_name", "Unknown"),
                    description=desc,
                    link=item.get("redirect_url", ""),
                    contact_email=_extract_email(desc),
                    source="Adzuna",
                    search_query=keywords,
                    location=location,
                ))
            page += 1
            if page > 3:   # cap at 3 pages
                break

        except requests.HTTPError as e:
            code = e.response.status_code
            if code == 401:
                raise RuntimeError("Adzuna: Invalid credentials — check Settings.")
            raise RuntimeError(f"Adzuna API error {code}")
        except requests.ConnectionError:
            raise RuntimeError("Adzuna: No internet connection.")
        except Exception as e:
            raise RuntimeError(f"Adzuna: {e}")

    return jobs


def _extract_email(text: str) -> Optional[str]:
    matches = re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text)
    filtered = [m for m in matches if not any(x in m.lower() for x in ["noreply", "example"])]
    return filtered[0] if filtered else None


def _detect_country(location: str) -> str:
    loc = location.lower()
    if any(x in loc for x in ["uk","england","london","manchester","birmingham","glasgow","edinburgh","bristol","liverpool","cardiff","belfast"]):
        return "gb"
    if any(x in loc for x in ["canada","toronto","vancouver","montreal","calgary","ottawa","edmonton"]):
        return "ca"
    if any(x in loc for x in ["australia","sydney","melbourne","brisbane","perth","adelaide"]):
        return "au"
    if any(x in loc for x in ["india","bangalore","bengaluru","mumbai","delhi","hyderabad","chennai","pune","kolkata"]):
        return "in"
    if any(x in loc for x in ["germany","berlin","munich","hamburg","frankfurt","cologne"]):
        return "de"
    if any(x in loc for x in ["france","paris","lyon","marseille"]):
        return "fr"
    if any(x in loc for x in ["netherlands","amsterdam","rotterdam"]):
        return "nl"
    if any(x in loc for x in ["singapore"]):
        return "sg"
    if any(x in loc for x in ["brazil","sao paulo","rio"]):
        return "br"
    if any(x in loc for x in ["south africa","cape town","johannesburg"]):
        return "za"
    if any(x in loc for x in ["poland","warsaw","krakow"]):
        return "pl"
    return "us"
