"""
Careerjet Partner API client (v4) — free publisher key required.

Careerjet is one of the largest job aggregators globally, with very strong
US coverage across onsite, hybrid, and remote roles.  It pulls from thousands
of company career pages and other boards, giving volume that complements the
tech-specific boards already in this stack.

Why include it:
- Genuine US onsite coverage — fills the gap left by remote-only boards.
- Broad industry coverage: engineering, data, product, finance, healthcare.
- Structured salary data: salary_min, salary_max, currency, and type (Y/M/W/D/H).
- RFC 2822 date strings — clean, parseable, reliable.

How to get your free publisher key:
  1. Go to https://www.careerjet.com/partners/register/as-publisher
  2. Register (takes < 2 minutes, free, no approval wait).
  3. Copy your API key from the publisher dashboard.
  4. Add it to .env as: CAREERJET_API_KEY=your_key_here

API reference: https://www.careerjet.com/partners/api
Endpoint:      https://search.api.careerjet.net/v4/query
Auth:          HTTP Basic — API key as username, empty password.
"""
from email.utils import parsedate_to_datetime
from typing import List, Optional

import requests

from config import CAREERJET_API_KEY
from database.models import Job
from utils.job_helpers import detect_h1b, extract_email, is_within_days

_URL = "https://search.api.careerjet.net/v4/query"

# Salary type codes returned by Careerjet → human-readable label
_SALARY_TYPE = {
    "Y": "yr",
    "M": "mo",
    "W": "wk",
    "D": "day",
    "H": "hr",
}

# Careerjet requires user_ip and user_agent on every request.
# For a server-side aggregator there is no real browser session, so we send
# a neutral placeholder that satisfies the API's validation without spoofing.
_PLACEHOLDER_IP    = "127.0.0.1"
_PLACEHOLDER_AGENT = "ResumeWing/1.0 (job aggregator; server-side)"


# ── Date parser ────────────────────────────────────────────────────────────────
# Careerjet returns RFC 2822 dates: "Wed, 15 Nov 2023 19:13:43 GMT"
# Python's email.utils.parsedate_to_datetime handles this format natively.

def _parse_careerjet_date(text: str) -> str:
    """Convert an RFC 2822 date string to YYYY-MM-DD, or '' on failure."""
    if not text:
        return ""
    try:
        return parsedate_to_datetime(text).strftime("%Y-%m-%d")
    except Exception:
        return ""


# ── Salary formatter ───────────────────────────────────────────────────────────

def _format_salary(item: dict) -> tuple:
    """
    Build a human-readable salary_text and extract numeric min/max from a
    Careerjet job dict.

    Returns (salary_text, salary_min, salary_max).
    """
    sal_min  = item.get("salary_min")
    sal_max  = item.get("salary_max")
    currency = (item.get("salary_currency_code") or "").upper() or "USD"
    sal_type = _SALARY_TYPE.get(item.get("salary_type", ""), "")

    # If the API already returned a formatted salary string, prefer it.
    raw_text = (item.get("salary") or "").strip()
    if raw_text:
        return raw_text, _to_float(sal_min), _to_float(sal_max)

    # Build from structured fields when salary text is absent.
    if sal_min and sal_max:
        text = f"{currency} {sal_min:,.0f} – {sal_max:,.0f}"
    elif sal_min:
        text = f"{currency} {sal_min:,.0f}+"
    elif sal_max:
        text = f"Up to {currency} {sal_max:,.0f}"
    else:
        text = ""

    if text and sal_type:
        text += f" / {sal_type}"

    return text, _to_float(sal_min), _to_float(sal_max)


def _to_float(val) -> Optional[float]:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


# ── Main fetch function ────────────────────────────────────────────────────────

def fetch(
    keywords: str,
    location: str,
    num_results: int = 20,
    date_filter: Optional[int] = None,
    job_type: Optional[str] = None,
) -> List[Job]:
    """
    Search Careerjet (v4) for jobs matching keywords + location.

    Args:
        keywords:    Job title or skill keywords.
        location:    US city/state string ("Austin, TX") or "Remote".
        num_results: Max jobs to return.
        date_filter: Max age in days for client-side filtering.
        job_type:    Employment type string for server-side contract_type filter.

    Returns:
        List of Job dataclass instances.

    Raises:
        RuntimeError: Propagated to aggregator for per-board error isolation.
    """
    if not CAREERJET_API_KEY:
        raise RuntimeError(
            "Careerjet API key not configured. "
            "Register free at https://www.careerjet.com/partners/register/as-publisher "
            "and add CAREERJET_API_KEY to your .env file."
        )

    location_lower = (location or "").lower().strip()
    is_remote      = location_lower in ("remote", "") or not location_lower
    search_location = "remote" if is_remote else location

    # Map our job_type string to Careerjet's contract_type parameter.
    # Careerjet accepts: p=permanent, c=contract, t=temporary, i=internship, v=volunteer
    contract_type = None
    if job_type:
        jt = job_type.lower()
        if jt in ("full-time", "fulltime", "permanent"):
            contract_type = "p"
        elif jt in ("contract", "contractor"):
            contract_type = "c"
        elif jt in ("part-time", "parttime", "temporary"):
            contract_type = "t"
        elif jt == "internship":
            contract_type = "i"

    # Request 2× what we need to have headroom after client-side date filtering.
    page_size = min(num_results * 2, 100)

    params: dict = {
        "keywords":    keywords,
        "location":    search_location,
        "locale_code": "en_US",
        "page_size":   page_size,
        "page":        1,
        "sort":        "date",
        "user_ip":     _PLACEHOLDER_IP,
        "user_agent":  _PLACEHOLDER_AGENT,
    }
    if contract_type:
        params["contract_type"] = contract_type

    try:
        # Careerjet v4 uses HTTP Basic auth: API key as username, empty password.
        response = requests.get(
            _URL,
            params=params,
            auth=(CAREERJET_API_KEY, ""),
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()

    except requests.HTTPError as exc:
        status = exc.response.status_code
        if status == 401:
            raise RuntimeError(
                "Careerjet: Invalid API key. "
                "Check CAREERJET_API_KEY in your .env file."
            )
        raise RuntimeError(f"Careerjet API error (HTTP {status})")
    except requests.ConnectionError:
        raise RuntimeError("Careerjet: No internet connection.")
    except Exception as exc:
        raise RuntimeError(f"Careerjet: {exc}")

    # Handle non-JOBS response types (LOCATIONS disambiguation, etc.)
    response_type = data.get("type", "")
    if response_type != "JOBS":
        msg = data.get("message", "unknown response")
        raise RuntimeError(f"Careerjet: Unexpected response — {msg}")

    postings = data.get("jobs") or []
    jobs: List[Job] = []

    for item in postings:
        if len(jobs) >= num_results:
            break

        # ── Date ──────────────────────────────────────────────────────────────
        date_str = _parse_careerjet_date(item.get("date", ""))
        if date_filter and date_str and not is_within_days(date_str, date_filter):
            continue

        # ── Salary ────────────────────────────────────────────────────────────
        sal_text, sal_min, sal_max = _format_salary(item)

        # ── Location ──────────────────────────────────────────────────────────
        loc_raw = (item.get("locations") or "").strip()
        is_remote_listing = is_remote or "remote" in loc_raw.lower()

        # ── Build Job ─────────────────────────────────────────────────────────
        desc = (item.get("description") or "").strip()

        jobs.append(Job(
            title         = (item.get("title")   or "").strip(),
            company       = (item.get("company") or "Unknown").strip(),
            description   = desc,
            link          = (item.get("url")     or "").strip(),
            contact_email = extract_email(desc),
            source        = "Careerjet",
            search_query  = keywords,
            location      = loc_raw or ("Remote" if is_remote_listing else ""),
            date_posted   = date_str,
            salary_text   = sal_text,
            salary_min    = sal_min,
            salary_max    = sal_max,
            remote        = is_remote_listing,
            h1b_mention   = detect_h1b(desc),
        ))

    return jobs
