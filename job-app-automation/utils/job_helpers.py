"""
Shared utilities used by all job board API clients and UI components.

These are pure functions with no side effects — safe to import anywhere.
"""
import re
from datetime import datetime, timezone
from typing import Optional


# ── H1B / visa sponsorship detection ──────────────────────────────────────────

_H1B_KEYWORDS = [
    "h1b", "h-1b", "h1-b", "visa sponsor", "will sponsor",
    "sponsorship available", "sponsorship provided", "sponsor work auth",
    "open to sponsorship", "work authorization sponsor", "work visa sponsor",
    "immigration sponsor", "h1 visa",
]


def detect_h1b(text: str) -> bool:
    """Return True if text mentions H1B or visa sponsorship."""
    t = text.lower()
    return any(kw in t for kw in _H1B_KEYWORDS)


# ── Email extraction ──────────────────────────────────────────────────────────

def extract_email(text: str) -> Optional[str]:
    """
    Extract the first plausible recruiter/contact email from text.
    Filters out common spam/noreply patterns.
    """
    matches = re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text)
    noise = ("noreply", "no-reply", "example", "test@", "donotreply", "notifications@")
    filtered = [m for m in matches if not any(n in m.lower() for n in noise)]
    return filtered[0] if filtered else None


# ── Date normalisation ────────────────────────────────────────────────────────

def normalize_date(value) -> Optional[str]:
    """
    Convert various date formats to a YYYY-MM-DD string.
    Accepts: ISO 8601, Unix epoch int/float, RFC 2822 string.
    Returns None if the input is empty or unparseable.
    """
    if not value:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%Y-%m-%d")

        s = str(value).strip()
        # Already YYYY-MM-DD — return directly.
        if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
            return s

        # ISO 8601 variants with time component.
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f%z",
        ):
            try:
                return datetime.strptime(s[:26], fmt[:len(fmt)]).strftime("%Y-%m-%d")
            except ValueError:
                pass

        # RFC 2822: "Mon, 15 Jan 2024 12:00:00 +0000"
        from email.utils import parsedate_to_datetime
        try:
            return parsedate_to_datetime(s).strftime("%Y-%m-%d")
        except Exception:
            pass

        # Fallback: grab leading YYYY-MM-DD if present.
        if re.match(r"^\d{4}-\d{2}-\d{2}", s):
            return s[:10]

    except Exception:
        pass
    return None


# ── Salary formatting ─────────────────────────────────────────────────────────

def salary_text(min_val, max_val, currency: str = "USD") -> Optional[str]:
    """
    Format a numeric salary range into a human-readable string.
    Returns None if both values are absent or zero.
    """
    if not min_val and not max_val:
        return None
    symbol = {"USD": "$", "GBP": "£", "EUR": "€"}.get(currency, f"{currency} ")
    try:
        lo = int(float(min_val)) if min_val else None
        hi = int(float(max_val)) if max_val else None
        if lo and hi:
            return f"{symbol}{lo:,} – {symbol}{hi:,}/yr"
        if lo:
            return f"{symbol}{lo:,}+/yr"
        if hi:
            return f"Up to {symbol}{hi:,}/yr"
    except (TypeError, ValueError):
        pass
    return None


# ── Date filtering ────────────────────────────────────────────────────────────

def is_within_days(date_str: Optional[str], days: int) -> bool:
    """
    Return True if date_str (YYYY-MM-DD) is within the last N days.
    Returns True for unknown dates so they are not incorrectly excluded.
    """
    if not date_str or not days:
        return True
    try:
        posted = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        delta  = datetime.now(tz=timezone.utc) - posted
        return delta.days <= days
    except Exception:
        return True


# ── Job freshness display ─────────────────────────────────────────────────────

def freshness_badge(date_posted: Optional[str]) -> str:
    """
    Return a coloured emoji badge string indicating how fresh a job listing is.

    Rules:
      🟢 Today / ≤3 days — Apply immediately, very fresh.
      🟡 4–7 days        — Still good, apply soon.
      🟠 8–14 days       — Getting older, prioritise.
      🔴 15–30 days      — May be expiring, verify before applying.
      ⛔ >30 days        — Likely expired; shown only if user opts in.

    Returns a plain string (not HTML) suitable for both markdown and st.caption().
    """
    if not date_posted:
        return "🕐 Posted date unknown"

    try:
        posted = datetime.strptime(date_posted, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        days   = (datetime.now(tz=timezone.utc) - posted).days
    except Exception:
        return "🕐 Posted date unknown"

    if days == 0:
        return "🟢 Posted today"
    if days == 1:
        return "🟢 Posted yesterday"
    if days <= 3:
        return f"🟢 {days}d ago"
    if days <= 7:
        return f"🟡 {days}d ago"
    if days <= 14:
        return f"🟠 {days}d ago"
    if days <= 30:
        return f"🔴 {days}d ago — verify before applying"
    return f"⛔ {days}d ago — may be expired"


def days_since_posted(date_posted: Optional[str]) -> Optional[int]:
    """Return the number of days since a job was posted, or None if unknown."""
    if not date_posted:
        return None
    try:
        posted = datetime.strptime(date_posted, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return (datetime.now(tz=timezone.utc) - posted).days
    except Exception:
        return None
