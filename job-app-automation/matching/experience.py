"""
Experience extraction and seniority classification.

Two signals are used (best available wins):
  1. Explicit mention  — "5+ years of experience" found in the resume text
  2. Date calculation  — earliest work-history year subtracted from today

Job seniority is inferred from job title keywords and, when those are absent,
from the experience-year requirements mentioned in the job description.
"""
import re
from datetime import datetime
from typing import Tuple

# ── Resume experience extraction ──────────────────────────────────────────────

_EXPLICIT_PATTERNS = [
    r'(\d+)\+?\s*(?:to\s*\d+\s*)?years?\s+(?:of\s+)?(?:professional\s+|total\s+|relevant\s+|industry\s+|work\s+)?experience',
    r'(\d+)\+?\s+years?\s+(?:in|working|of|as)\b',
    r'\bover\s+(\d+)\s+years?\b',
    r'(\d+)\+\s*years?\s+(?:track\s+record|background)',
]

_CURRENT_YEAR = datetime.now().year


def extract_years_of_experience(resume_text: str) -> Tuple[int, str]:
    """
    Return (years: int, method: str) where method is one of:
      "explicit"   — found a literal "X years of experience" statement
      "calculated" — derived from the span of work-history dates in the text
      "unknown"    — could not determine

    The result is capped at 40 years and zero-floored.
    """
    text_lower = resume_text.lower()

    # Method 1: explicit sentence
    for pattern in _EXPLICIT_PATTERNS:
        m = re.search(pattern, text_lower)
        if m:
            years = int(m.group(1))
            if 1 <= years <= 40:
                return years, "explicit"

    # Method 2: span of dates in work history
    calc = _years_from_dates(text_lower)
    if calc > 0:
        return calc, "calculated"

    return 0, "unknown"


def _years_from_dates(text_lower: str) -> int:
    """
    Scan the resume for work-history year mentions and compute
    (current_year − earliest_start_year).  Only considers 4-digit years
    between 1985 and current year to avoid false positives.
    """
    years_found = []

    # "Month YYYY" pattern
    month_year = re.findall(
        r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+((?:19|20)\d{2})',
        text_lower,
    )
    for y in month_year:
        yr = int(y)
        if 1985 <= yr <= _CURRENT_YEAR:
            years_found.append(yr)

    # "YYYY –/- YYYY" or "YYYY – present/current/now"
    year_range = re.findall(
        r'((?:19|20)\d{2})\s*[-–—]\s*(?:present|current|now|(?:19|20)\d{2})',
        text_lower,
    )
    for y in year_range:
        yr = int(y)
        if 1985 <= yr <= _CURRENT_YEAR:
            years_found.append(yr)

    if not years_found:
        return 0

    earliest = min(years_found)
    span = _CURRENT_YEAR - earliest
    return max(0, min(span, 40))


# ── Level classification ───────────────────────────────────────────────────────

def classify_user_level(years: int) -> str:
    """
    Map raw years → a human level label used for matching.

    0–1  → intern
    2–4  → entry
    5–8  → mid
    9+   → senior
    """
    if years <= 1:
        return "intern"
    if years <= 4:
        return "entry"
    if years <= 8:
        return "mid"
    return "senior"


# Title keywords for job level detection
_SENIOR_KEYS = frozenset({
    "senior", "sr.", "sr ", "lead", "principal", "staff", "director",
    "head of", "vp ", "v.p.", "architect", "chief", "manager", "distinguished",
    "level 5", "level 6", "level 7", "l5", "l6", "l7",
})
_ENTRY_KEYS = frozenset({
    "junior", "jr.", "jr ", "associate", "entry", "intern", "trainee",
    "graduate", "new grad", "early career", "entry-level",
    "level 1", "level 2", "l1", "l2", " i ", "-i-", " i$",
})
_MID_KEYS = frozenset({
    "mid ", "mid-", "midlevel", "mid level", "intermediate",
    "level 3", "level 4", "l3", "l4", " ii ", " iii ",
})


def classify_job_level(title: str, description: str = "") -> str:
    """
    Classify the required seniority level of a job posting.

    Returns: "intern" | "entry" | "mid" | "senior" | "any"

    The title is the primary signal.  When no title-level keyword is found we
    scan the first 600 characters of the description for an explicit years
    requirement (e.g. "5+ years of experience").
    """
    title_l = (" " + title.lower() + " ")

    if any(k in title_l for k in _SENIOR_KEYS):
        return "senior"
    if any(k in title_l for k in _ENTRY_KEYS):
        return "entry"
    if any(k in title_l for k in _MID_KEYS):
        return "mid"

    # Fall back to description years requirement
    desc_snippet = (description or "")[:600].lower()
    m = re.search(
        r'(\d+)\+?\s*(?:to\s*\d+\s*)?years?\s+(?:of\s+)?(?:professional\s+|relevant\s+)?experience',
        desc_snippet,
    )
    if m:
        req = int(m.group(1))
        if req >= 7:
            return "senior"
        if req >= 4:
            return "mid"
        if req >= 1:
            return "entry"

    return "any"


# Adjacency table: which job levels are acceptable for each user level
_LEVEL_ADJACENCY: dict = {
    "intern": {"intern", "entry", "any"},
    "entry":  {"intern", "entry", "mid", "any"},
    "mid":    {"entry",  "mid",   "senior", "any"},
    "senior": {"mid",    "senior", "any"},
}


def is_experience_match(user_years: int, job_title: str, job_description: str = "") -> bool:
    """
    Return True if this job is a reasonable experience-level fit for the user.

    We use one-level adjacency so a mid-level developer sees both entry and
    senior postings — this avoids overly aggressive filtering.
    Unknown user experience (0 years) always returns True.
    """
    if user_years == 0:
        return True  # unknown → show everything

    user_level = classify_user_level(user_years)
    job_level  = classify_job_level(job_title, job_description)
    return job_level in _LEVEL_ADJACENCY.get(user_level, {"any"})
