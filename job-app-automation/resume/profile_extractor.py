"""
Resume → Structured Autofill Profile Extractor
===============================================
Parses raw resume text into a clean, structured JSON profile.
This profile is the single source of truth the browser extension reads
to auto-fill job application forms on Greenhouse, Lever, Workday, etc.

Design principles
-----------------
- Every public field has a stable key name; the extension's selector-map
  references keys like "first_name", "email", "work_experience[0].company"
  directly — renaming a key here is a breaking change.
- Fields that cannot be extracted reliably are returned as empty strings
  (never None/null) so the extension never needs null-checks.
- All extraction is regex + heuristic — no AI calls, so this is fast
  and works fully offline without the sentence-transformer model loaded.
- The caller (main.py) supplies the stored user profile dict so manual
  overrides (candidate_name, work_authorization choice, etc.) win over
  the parsed values.

Exported
--------
  extract_autofill_profile(resume_text, raw_skills, stored_profile) -> dict
"""
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple


# ── US state code ↔ full name lookup ──────────────────────────────────────────

_STATE_MAP: Dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}

_STATE_CODES = "|".join(_STATE_MAP.keys())


def _state_full(code: str) -> str:
    return _STATE_MAP.get(code.upper(), code)


# ── Month helpers ─────────────────────────────────────────────────────────────

_MONTHS: Dict[str, Tuple[str, str]] = {
    "jan": ("January",   "01"), "feb": ("February",  "02"), "mar": ("March",     "03"),
    "apr": ("April",     "04"), "may": ("May",        "05"), "jun": ("June",      "06"),
    "jul": ("July",      "07"), "aug": ("August",     "08"), "sep": ("September", "09"),
    "oct": ("October",   "10"), "nov": ("November",   "11"), "dec": ("December",  "12"),
}

# Matches "Jan 2022", "January 2022", "Jan, 2022", "2022-01", bare "2022"
_DATE_TOKEN = (
    r"(?:"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*[\s,]+(?:20|19)\d{2}"  # Month YYYY
    r"|(?:20|19)\d{2}-(?:0[1-9]|1[0-2])"                                           # YYYY-MM
    r"|(?:20|19)\d{2}"                                                               # bare YYYY
    r")"
)

# Full date-range pattern: "<start> – <end_or_present>"
_DATE_RANGE_RE = re.compile(
    rf"({_DATE_TOKEN})\s*[-–—]\s*({_DATE_TOKEN}|present|current|now)",
    re.I,
)


def _parse_date_token(token: str) -> Dict[str, str]:
    """
    Parse a date token into {month, month_num, year}.
    All values are strings; missing parts are empty string.
    """
    t = token.strip().lower()

    # "Month YYYY"
    m = re.match(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*[\s,]+(\d{4})", t)
    if m:
        abbr = m.group(1)[:3]
        month_full, month_num = _MONTHS[abbr]
        return {"month": month_full, "month_num": month_num, "year": m.group(2)}

    # "YYYY-MM"
    m = re.match(r"(\d{4})-(\d{2})", t)
    if m:
        yr, mn = m.group(1), m.group(2)
        for abbr, (mf, mn2) in _MONTHS.items():
            if mn2 == mn:
                return {"month": mf, "month_num": mn, "year": yr}

    # Bare year
    m = re.search(r"\b(\d{4})\b", t)
    if m:
        return {"month": "", "month_num": "", "year": m.group(1)}

    return {"month": "", "month_num": "", "year": ""}


# ── Personal info extraction ──────────────────────────────────────────────────

_CONTACT_SKIP = re.compile(
    r"@|http|linkedin|github|phone|email|fax|\(\d{3}\)|resume|curriculum",
    re.I,
)
_SECTION_HEADER = re.compile(
    r"^(summary|objective|experience|education|skills|profile|projects|"
    r"certifications?|awards?|publications?|interests?|references?)$",
    re.I,
)


def _extract_name(text: str) -> Dict[str, str]:
    """
    Heuristic: the candidate's name is typically the first non-contact,
    non-header line that consists of 2–4 title-cased words.
    """
    blank = {"full_name": "", "first_name": "", "last_name": "", "middle_name": ""}
    for line in text.splitlines()[:15]:
        line = line.strip()
        if not line or _CONTACT_SKIP.search(line) or _SECTION_HEADER.match(line):
            continue
        words = line.split()
        if 2 <= len(words) <= 4:
            # Each word: starts uppercase, rest lower or hyphens/apostrophes
            if all(re.match(r"^[A-Z][a-zA-Z''-]+$", w) for w in words):
                return {
                    "full_name":   line,
                    "first_name":  words[0],
                    "last_name":   words[-1],
                    "middle_name": " ".join(words[1:-1]) if len(words) > 2 else "",
                }
    return blank


def _extract_phone(text: str) -> Tuple[str, str]:
    """
    Return (formatted, digits_only) for the first phone number found.
    formatted → "(555) 123-4567"   digits_only → "5551234567"
    """
    pattern = re.compile(
        r"(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}"
    )
    m = pattern.search(text)
    if not m:
        return "", ""
    raw   = m.group(0)
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}", digits
    return raw, digits


def _extract_email(text: str) -> str:
    m = re.search(r"[\w.+%-]+@[\w-]+\.[\w.]+", text)
    return m.group(0).lower() if m else ""


def _extract_location(text: str) -> Dict[str, str]:
    """
    Extract city, state (code + full name), zip from resume.
    Handles "Austin, TX 78701" and "Austin, Texas" patterns.

    NOTE: patterns use [a-zA-Z ]+ (no \\n) so they never span across lines.
    """
    empty = {"city": "", "state": "", "state_full": "", "zip": "", "country": ""}

    # "City, ST 12345" — state code form  (city: 2-25 non-newline chars)
    m = re.search(
        rf"([A-Z][a-zA-Z ]{{1,24}}),[ \t]*({_STATE_CODES})\b[ \t]*(\d{{5}}(?:-\d{{4}})?)?",
        text,
    )
    if m:
        return {
            "city":       m.group(1).strip(),
            "state":      m.group(2),
            "state_full": _state_full(m.group(2)),
            "zip":        m.group(3) or "",
            "country":    "United States",
        }

    # "City, Full State Name"
    state_names = "|".join(re.escape(v) for v in _STATE_MAP.values())
    m = re.search(
        rf"([A-Z][a-zA-Z ]{{1,24}}),[ \t]*({state_names})\b",
        text,
    )
    if m:
        city  = m.group(1).strip()
        sfull = m.group(2).strip()
        scode = next((k for k, v in _STATE_MAP.items() if v == sfull), sfull)
        return {"city": city, "state": scode, "state_full": sfull, "zip": "", "country": "United States"}

    return empty


def _extract_links(text: str, pdf_hyperlinks: Optional[List[str]] = None) -> Dict[str, str]:
    """
    Extract LinkedIn, GitHub, and personal portfolio/website URLs.

    Two sources, in priority order:
      1. `pdf_hyperlinks` — clean URIs from PDF link annotations. Always
         correct (no PDF text-engine artifacts), so we check these first.
      2. Resume text — fallback regex over the visible glyphs. Tolerates
         whitespace artifacts ("linkedin. com / in / X") that PDF extraction
         sometimes inserts.
    """
    result = {"linkedin": "", "github": "", "portfolio": ""}

    excluded_for_portfolio = (
        "linkedin", "github", "gmail", "mailto", "twitter", "x.com",
        "facebook", "instagram", "youtube", "leetcode", "stackoverflow",
        "google.com", "medium.com",
    )

    def _consider(url: str) -> None:
        """Classify a single URL into linkedin / github / portfolio."""
        clean = url.strip().rstrip(".,;:)")
        if not clean:
            return
        low = clean.lower()
        if "linkedin.com/" in low and not result["linkedin"]:
            slug_m = re.search(r"linkedin\.com/(?:in|pub)/([A-Za-z0-9._-]+)", clean, re.I) \
                  or re.search(r"linkedin\.com/([A-Za-z0-9._-]+)", clean, re.I)
            if slug_m:
                slug = slug_m.group(1).rstrip(".,;:)/")
                if slug.lower() not in {"company", "learning", "feed", "jobs", "in"}:
                    result["linkedin"] = f"https://www.linkedin.com/in/{slug}"
            return
        if "github.com/" in low and not result["github"]:
            slug_m = re.search(r"github\.com/([A-Za-z0-9_-]+)", clean, re.I)
            if slug_m:
                slug = slug_m.group(1).rstrip(".,;:)/")
                if slug.lower() not in {"orgs", "topics", "marketplace", "explore"}:
                    result["github"] = f"https://github.com/{slug}"
            return
        if (low.startswith("http://") or low.startswith("https://")) and not result["portfolio"]:
            if not any(x in low for x in excluded_for_portfolio):
                result["portfolio"] = clean

    # ── 1. Authoritative PDF link annotations ────────────────────────────────
    for uri in (pdf_hyperlinks or []):
        _consider(uri)

    # ── 2. Fallback: regex over text (handles PDF whitespace quirks) ──────────
    if not (result["linkedin"] and result["github"] and result["portfolio"]):
        # Light normalization: only collapse spaces between word + dot + word
        # (e.g. "linkedin. com" → "linkedin.com"). Do NOT collapse newlines —
        # that previously caused "https://X/\nhttps://Y" to merge into
        # "https://X/https://Y".
        normalized = re.sub(r"([A-Za-z])[ \t]+(\.[ \t]*[A-Za-z])", r"\1\2", text)
        normalized = re.sub(r"([A-Za-z])[ \t]*\.[ \t]+([A-Za-z])", r"\1.\2", normalized)

        if not result["linkedin"]:
            li = (
                re.search(r"linkedin\.com/(?:in|pub)/([A-Za-z0-9._-]+)", normalized, re.I)
                or re.search(r"linkedin\.com/([A-Za-z0-9._-]+)", normalized, re.I)
            )
            if li:
                slug = li.group(1).rstrip(".,;:)/")
                if slug.lower() not in {"company", "learning", "feed", "jobs", "in"}:
                    result["linkedin"] = f"https://www.linkedin.com/in/{slug}"

        if not result["github"]:
            gh = re.search(r"github\.com/([A-Za-z0-9_-]+)", normalized, re.I)
            if gh:
                slug = gh.group(1).rstrip(".,;:)/")
                if slug.lower() not in {"orgs", "topics", "marketplace", "explore"}:
                    result["github"] = f"https://github.com/{slug}"

        if not result["portfolio"]:
            for url in re.findall(r"https?://[A-Za-z0-9.\-]+\.[a-z]{2,}[\w/.\-?=&%]*", normalized, re.I):
                _consider(url)
                if result["portfolio"]:
                    break

    return result


# ── Work experience extraction ────────────────────────────────────────────────

_BULLET_RE    = re.compile(r"^[•\-\*▪►→◦▶⦿⁃✓✔]\s*")
_DIVIDER_CHAR = re.compile(r"\s*[|·•·@]\s*")


def _split_title_company(text: str) -> Tuple[str, str]:
    """
    Try to split "Title | Company" or "Title at Company" or "Title, Company".
    Returns (title, company); if split fails returns (text, "").
    """
    # "Title | Company" or "Title · Company"
    parts = _DIVIDER_CHAR.split(text, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return parts[0].strip(), parts[1].strip()

    # "Title at Company Name"
    m = re.match(r"^(.+?)\s+at\s+(.+)$", text, re.I)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    return text.strip(), ""


def _is_company_like(line: str) -> bool:
    """
    Heuristic: a company name is a short (≤6 words), not-all-lowercase line
    that doesn't start with a bullet or look like a description sentence.
    """
    words = line.split()
    if not words or len(words) > 8:
        return False
    if line[0].islower():
        return False
    if line.endswith((".", ",")):
        return False
    return True


def _extract_work_experience(experience_text: str) -> List[Dict]:
    """
    Parse the Experience section into a structured list of job entries.

    State machine strategy
    ----------------------
    1. Lines before the FIRST date range → buffered as `pending_header_lines`
       (they belong to the first entry's title / company).
    2. A date-range line triggers a new entry:
       a. The pending_header_lines are consumed to fill title / company / location.
       b. Any text on the same line BEFORE the date range is also parsed.
    3. Inside an entry:
       - Bullet-marker lines  → `current_bullets`.
       - Short non-bullet lines that appear AFTER the first bullet → routed
         into `pending_header_lines` for the NEXT entry (they are the next
         job's title / company, not part of the current body).
       - Short non-bullet lines BEFORE the first bullet → fill current
         entry's missing company / title.
       - Long lines (>60 chars) before the first bullet → description text.

    Returns list of dicts with stable keys used by the extension.
    """
    if not experience_text.strip():
        return []

    lines = [l.rstrip() for l in experience_text.splitlines()]
    entries: List[Dict] = []
    pending_header_lines: List[str] = []   # buffered lines for the NEXT entry's header
    current: Optional[Dict] = None
    current_bullets: List[str] = []
    current_desc_lines: List[str] = []
    seen_bullet_in_current = False         # True once the first bullet is found

    def _close_current():
        nonlocal current, current_bullets, current_desc_lines, seen_bullet_in_current
        if current is None:
            return
        current["bullets"]     = current_bullets[:]
        current["description"] = " ".join(current_desc_lines).strip()
        entries.append(current)
        current = None
        current_bullets = []
        current_desc_lines = []
        seen_bullet_in_current = False

    _loc_inline_re = re.compile(
        rf"([A-Z][a-zA-Z ]{{1,24}}),[ \t]*({_STATE_CODES})\b"
    )

    def _consume_headers(entry: Dict, header_lines: List[str]) -> None:
        """
        Assign pending header lines to the entry's title / company / location.
        Order is ambiguous in real resumes (some put title first, some company
        first), so we use heuristics applied in priority order:
          1. "Company | City, ST" or "Title | Company, Location" — split on pipe
             and check whether each part is a location, company, or title.
          2. A standalone "City, ST" line → location.
          3. The first unconsumed short line → title.
          4. A subsequent short line → company.
        """
        for hl in header_lines:
            hl = hl.strip()
            if not hl:
                continue

            # ── Pipe-separated line: "TechCorp Inc | Austin, TX"
            #    or "Senior Engineer | TechCorp | Remote"
            if re.search(r"[|·]", hl):
                parts = re.split(r"\s*[|·]\s*", hl)
                # Identify which part is a location
                loc_part_idx = -1
                for idx, part in enumerate(parts):
                    if _loc_inline_re.search(part):
                        loc_part_idx = idx
                        break

                if loc_part_idx >= 0:
                    # The location part is found; remaining parts are title/company
                    if not entry["location"]:
                        entry["location"] = parts[loc_part_idx].strip()
                    others = [p.strip() for i, p in enumerate(parts) if i != loc_part_idx and p.strip()]
                    for part in others:
                        if not entry["title"]:
                            entry["title"] = part
                        elif not entry["company"] and _is_company_like(part):
                            entry["company"] = part
                else:
                    # No location part — treat as "Title | Company"
                    t, c = _split_title_company(hl)
                    if not entry["title"]:
                        entry["title"] = t
                    if not entry["company"]:
                        entry["company"] = c
                continue

            # ── Standalone location line: "Austin, TX 78701"
            if _loc_inline_re.search(hl) and len(hl.split()) <= 5:
                if not entry["location"]:
                    entry["location"] = hl
                continue

            # ── Plain title / company line
            if not entry["title"]:
                entry["title"] = hl
            elif not entry["company"] and _is_company_like(hl):
                entry["company"] = hl

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        dm = _DATE_RANGE_RE.search(stripped)
        if dm and len(stripped) < 120:
            # ── New experience entry starts here ──────────────────────────
            _close_current()

            start_raw  = dm.group(1)
            end_raw    = dm.group(2)
            is_current = end_raw.strip().lower() in ("present", "current", "now")

            sp = _parse_date_token(start_raw)
            ep = {} if is_current else _parse_date_token(end_raw)

            current = {
                "company":         "",
                "title":           "",
                "location":        "",
                "start_month":     sp.get("month", ""),
                "start_month_num": sp.get("month_num", ""),
                "start_year":      sp.get("year", ""),
                "end_month":       "" if is_current else ep.get("month", ""),
                "end_month_num":   "" if is_current else ep.get("month_num", ""),
                "end_year":        "" if is_current else ep.get("year", ""),
                "is_current":      is_current,
                "bullets":         [],
                "description":     "",
            }

            # Text on the same line BEFORE the date range
            before = stripped[:dm.start()].strip().rstrip("|·—–- ").strip()
            if before:
                t, c = _split_title_company(before)
                current["title"]   = t
                current["company"] = c

            # Consume buffered header lines
            _consume_headers(current, pending_header_lines)
            pending_header_lines = []

        elif current is None:
            # Before the very first entry — buffer for upcoming entry's header
            pending_header_lines.append(stripped)

        else:
            # ── Inside an experience entry ────────────────────────────────
            is_bullet = bool(_BULLET_RE.match(stripped))

            if is_bullet:
                clean = _BULLET_RE.sub("", stripped).strip()
                if clean:
                    current_bullets.append(clean)
                seen_bullet_in_current = True

            elif seen_bullet_in_current:
                # Lines AFTER the first bullet almost always belong to the
                # NEXT entry's header (next company/title), not this entry.
                pending_header_lines.append(stripped)

            else:
                # Lines BEFORE the first bullet — try to fill current entry
                if len(stripped) > 60:
                    # Paragraph description line
                    current_desc_lines.append(stripped)
                elif not current["company"] and _is_company_like(stripped):
                    current["company"] = stripped
                elif not current["title"] and len(stripped.split()) <= 10:
                    current["title"] = stripped

    _close_current()
    return entries


# ── Education extraction ──────────────────────────────────────────────────────

_DEGREE_PATTERNS = [
    (re.compile(r"\b(b\.?s\.?|bachelor\s+of\s+science)\b", re.I),          "Bachelor of Science",  "B.S."),
    (re.compile(r"\b(b\.?a\.?|bachelor\s+of\s+arts)\b", re.I),             "Bachelor of Arts",     "B.A."),
    (re.compile(r"\b(b\.?e\.?|b\.?eng\.?|bachelor\s+of\s+engineering)\b", re.I), "Bachelor of Engineering", "B.E."),
    (re.compile(r"\bbachelor\b", re.I),                                     "Bachelor's Degree",    "B.S."),
    (re.compile(r"\b(m\.?s\.?|master\s+of\s+science)\b", re.I),            "Master of Science",    "M.S."),
    (re.compile(r"\b(m\.?a\.?|master\s+of\s+arts)\b", re.I),               "Master of Arts",       "M.A."),
    (re.compile(r"\b(m\.?b\.?a\.?)\b", re.I),                              "Master of Business Administration", "MBA"),
    (re.compile(r"\b(m\.?eng\.?|master\s+of\s+engineering)\b", re.I),      "Master of Engineering","M.Eng."),
    (re.compile(r"\bmaster\b", re.I),                                       "Master's Degree",      "M.S."),
    (re.compile(r"\b(ph\.?d\.?|doctor\s+of\s+philosophy)\b", re.I),        "Doctor of Philosophy",  "Ph.D."),
    (re.compile(r"\b(a\.?s\.?|associate\s+of\s+science)\b", re.I),         "Associate of Science",  "A.S."),
    (re.compile(r"\bassociate\b", re.I),                                    "Associate's Degree",    "A.S."),
]


def _extract_education(education_text: str) -> List[Dict]:
    """
    Parse the Education section into a list of degree entries.

    Each entry has stable keys that map directly to common ATS form fields:
      school, degree, degree_short, major, graduation_year, gpa, is_current
    """
    if not education_text.strip():
        return []

    entries: List[Dict] = []
    current: Optional[Dict] = None

    def _new_entry() -> Dict:
        return {
            "school":           "",
            "degree":           "",
            "degree_short":     "",
            "major":            "",
            "graduation_month": "",
            "graduation_year":  "",
            "gpa":              "",
            "is_current":       False,
        }

    def _close():
        nonlocal current
        if current and (current["school"] or current["degree"]):
            entries.append(current)
        current = None

    for line in education_text.splitlines():
        stripped = line.strip()
        if not stripped or len(stripped) < 3:
            continue

        # Degree keyword found → new entry
        degree_label, degree_short = "", ""
        for pattern, full, short in _DEGREE_PATTERNS:
            if pattern.search(stripped):
                degree_label, degree_short = full, short
                break

        year_m = re.search(r"\b(20\d{2}|19\d{2})\b", stripped)
        gpa_m  = re.search(r"\bgpa[\s:]*([0-9]\.[0-9]{1,2})\b", stripped, re.I)
        major_m = re.search(
            r"\bin\s+([A-Z][A-Za-z\s&/]+?)(?:\s*[,(|]|\s*$)", stripped
        )

        if degree_label:
            _close()
            current = _new_entry()
            current["degree"]       = degree_label
            current["degree_short"] = degree_short
            if major_m:
                current["major"] = major_m.group(1).strip()
            if year_m:
                current["graduation_year"] = year_m.group(1)
            if gpa_m:
                current["gpa"] = gpa_m.group(1)
            current["is_current"] = bool(
                re.search(r"\b(present|current|ongoing|expected)\b", stripped, re.I)
            )
            continue

        if current is None:
            current = _new_entry()

        # Fill in school, year, gpa, major if not yet set
        if year_m and not current["graduation_year"]:
            current["graduation_year"] = year_m.group(1)
            current["is_current"] = bool(
                re.search(r"\b(present|current|ongoing|expected)\b", stripped, re.I)
            )

        if gpa_m and not current["gpa"]:
            current["gpa"] = gpa_m.group(1)

        if major_m and not current["major"]:
            current["major"] = major_m.group(1).strip()

        # Short lines that haven't been consumed → likely the school name
        if (not current["school"]
                and len(stripped.split()) <= 8
                and not gpa_m
                and not year_m
                and not _BULLET_RE.match(stripped)):
            current["school"] = stripped

    _close()
    return entries


# ── Summary extraction ────────────────────────────────────────────────────────

def _extract_summary(sections: Dict[str, str]) -> str:
    """Return the first ~3 sentences of the Summary / Objective section."""
    text = (sections.get("summary") or sections.get("objective") or "").strip()
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(sentences[:3])[:600].strip()


# ── Certifications extraction ─────────────────────────────────────────────────

def _extract_certifications(cert_text: str) -> List[Dict]:
    """
    Parse certifications section into a list of
    {name, issuer, year, credential_id} dicts.
    """
    if not cert_text.strip():
        return []

    certs: List[Dict] = []
    for line in cert_text.splitlines():
        stripped = _BULLET_RE.sub("", line.strip())
        if not stripped or len(stripped) < 4:
            continue

        year_m = re.search(r"\b(20\d{2}|19\d{2})\b", stripped)
        year   = year_m.group(1) if year_m else ""
        name   = stripped[:year_m.start()].strip().rstrip(",-") if year_m else stripped

        # "Name — Issuer" or "Name by Issuer" or "Name (Issuer)"
        issuer = ""
        m = re.split(r"\s*[-–]\s*|\s+by\s+|\s*\(", name, maxsplit=1)
        if len(m) == 2:
            name   = m[0].strip()
            issuer = m[1].strip().rstrip(")")

        # Credential ID sometimes appears as "#ABC123" or "ID: ABC123"
        cred_m = re.search(r"(?:credential\s*(?:id)?|#)\s*:?\s*([\w-]+)", stripped, re.I)

        if name:
            certs.append({
                "name":          name,
                "issuer":        issuer,
                "year":          year,
                "credential_id": cred_m.group(1) if cred_m else "",
            })

    return certs


# ── School name supplementary scan ───────────────────────────────────────────

# Common institution keywords that signal a school name line
_SCHOOL_KEYWORDS = re.compile(
    r"\b(university|college|institute|school|academy|polytechnic|seminary|"
    r"conservatory|community college)\b",
    re.I,
)


def _find_schools_in_raw(raw_text: str) -> List[str]:
    """
    Scan raw resume text for lines that look like school names.
    Returns them in order of appearance so callers can match them to
    education entries by proximity.
    """
    schools: List[str] = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if stripped and _SCHOOL_KEYWORDS.search(stripped) and len(stripped.split()) <= 10:
            schools.append(stripped)
    return schools


def _backfill_school_names(
    education_entries: List[Dict], raw_text: str
) -> List[Dict]:
    """
    For every education entry that is missing a school name, try to find
    one in the raw resume text using institution keywords.
    This compensates for parse_resume_sections occasionally dropping the
    school line (e.g. when it matches a section-boundary pattern).
    """
    if all(e["school"] for e in education_entries):
        return education_entries   # nothing to do

    schools_found = _find_schools_in_raw(raw_text)
    school_pool   = list(schools_found)   # consume one per blank entry

    for entry in education_entries:
        if not entry["school"] and school_pool:
            entry["school"] = school_pool.pop(0)

    return education_entries


# ── Skills flat list ──────────────────────────────────────────────────────────

def _build_skills_list(skills_section: str, raw_skills: List[str]) -> List[str]:
    """
    Return a clean, deduplicated list of skill strings.
    Prefers the parser-extracted raw_skills (already vocabulary-matched);
    falls back to splitting the skills section text.
    """
    if raw_skills:
        return sorted(set(s.strip() for s in raw_skills if s.strip()))

    if not skills_section.strip():
        return []

    text = re.sub(r"[•\-\*▪►→|/\\]", ",", skills_section)
    items = [s.strip() for s in re.split(r"[,\n]", text) if s.strip()]
    return sorted(set(s for s in items if 1 < len(s) <= 60))


# ── Main public function ──────────────────────────────────────────────────────

def extract_autofill_profile(
    resume_text: str,
    raw_skills: List[str],
    stored_profile: Dict[str, str],
    pdf_hyperlinks: Optional[List[str]] = None,
) -> Dict:
    """
    Parse resume text + stored user profile into the structured autofill
    profile returned by GET /profile/autofill.

    Args:
        resume_text:    Raw text from the uploaded PDF/DOCX.
        raw_skills:     Skills already extracted by utils/parser.py.
        stored_profile: Dict from the user_profile DB table.
        pdf_hyperlinks: List of URIs pulled from PDF link annotations
                        (page.get_links()). When present these are the
                        authoritative source for LinkedIn/GitHub/portfolio
                        URLs — text-fallback regex is only used to fill
                        gaps. Pass an empty list / None for DOCX uploads.

    Returns:
        Nested dict with all fields needed by the browser extension.
        Every leaf value is a string, int, bool, or list — never None.
    """
    from ats.scanner import parse_resume_sections
    from matching.experience import extract_years_of_experience, classify_user_level

    sections = parse_resume_sections(resume_text)

    name    = _extract_name(resume_text)
    email   = _extract_email(resume_text)
    phone_f, phone_d = _extract_phone(resume_text)
    loc     = _extract_location(resume_text)
    links   = _extract_links(resume_text, pdf_hyperlinks=pdf_hyperlinks)
    summary = _extract_summary(sections)

    work_exp  = _extract_work_experience(sections.get("experience", ""))
    education = _extract_education(sections.get("education", ""))
    education = _backfill_school_names(education, resume_text)
    skills    = _build_skills_list(sections.get("skills", ""), raw_skills)
    certs     = _extract_certifications(sections.get("certifications", ""))

    years, exp_method = extract_years_of_experience(resume_text)
    level = classify_user_level(years)

    # ── Stored profile overrides (user-set values always win) ──────────────────
    if stored_profile.get("candidate_name", "").strip():
        full = stored_profile["candidate_name"].strip()
        parts = full.split()
        # 1 word → only first name; 2 words → first + last; 3+ → first + middle(s) + last.
        # Previously we used split(None, 1) which jammed the middle name into
        # last_name (e.g. "Vageesh Kudutini Ramesh" → last="Kudutini Ramesh").
        if len(parts) == 1:
            name["first_name"]  = parts[0]
            name["middle_name"] = ""
            name["last_name"]   = ""
        elif len(parts) == 2:
            name["first_name"]  = parts[0]
            name["middle_name"] = ""
            name["last_name"]   = parts[1]
        else:
            name["first_name"]  = parts[0]
            name["last_name"]   = parts[-1]
            name["middle_name"] = " ".join(parts[1:-1])
        name["full_name"] = full

    if stored_profile.get("candidate_email", "").strip():
        email = stored_profile["candidate_email"].strip()

    # ── Assemble final profile ────────────────────────────────────────────────
    return {
        "personal": {
            "first_name":   name["first_name"],
            "last_name":    name["last_name"],
            "middle_name":  name.get("middle_name", ""),
            "full_name":    name["full_name"],
            "email":        email,
            "phone":        phone_f,          # "(555) 123-4567"
            "phone_digits": phone_d,          # "5551234567"  — for programmatic use
            "city":         loc["city"],
            "state":        loc["state"],     # "TX"
            "state_full":   loc["state_full"],# "Texas"
            "zip":          loc["zip"],
            "country":      loc.get("country", "United States"),
        },
        "links": {
            "linkedin":  links["linkedin"],
            "github":    links["github"],
            "portfolio": links["portfolio"],
        },
        "summary": summary,
        "work_experience": work_exp,
        "education":       education,
        "skills":          skills,
        "certifications":  certs,
        "preferences": {
            # Booleans stored as "true"/"false" strings in SQLite
            "work_authorized":      stored_profile.get("work_authorized", "true") != "false",
            "requires_sponsorship": stored_profile.get("requires_sponsorship", "false") == "true",
            "expected_salary":      stored_profile.get("expected_salary", ""),
            "willing_to_relocate":  stored_profile.get("willing_to_relocate", "false") == "true",
            "notice_period_days":   int(stored_profile.get("notice_period_days", "0") or "0"),
        },
        "metadata": {
            "years_experience":  years,
            "experience_level":  level,
            "experience_method": exp_method,
            "skills_count":      len(skills),
            "work_entries":      len(work_exp),
            "parsed_at":         datetime.now().isoformat(),
        },
    }
