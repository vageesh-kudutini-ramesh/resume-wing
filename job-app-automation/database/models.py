"""
Database model dataclasses for ResumeWing.

These are plain Python dataclasses — no ORM, no magic.
All persistence logic lives in db.py; models are just typed data containers.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Resume:
    id:          Optional[int] = None
    filename:    str = ""
    text:        str = ""
    skills:      str = "[]"         # JSON-encoded list of skill strings
    uploaded_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Job:
    # ── Identity ────────────────────────────────────────────────────────────────
    id:            Optional[int] = None
    title:         str = ""
    company:       str = ""
    description:   str = ""
    link:          str = ""         # Primary apply URL (unique constraint in DB)
    contact_email: Optional[str] = None
    source:        str = ""         # Board name: "JSearch", "Adzuna", "USAJobs", etc.

    # ── AI scores ───────────────────────────────────────────────────────────────
    match_score:   float = 0.0      # 0–100, cosine similarity vs. resume
    ats_score:     Optional[float] = None   # 0–100, set when user runs ATS scan

    # ── Workflow state ──────────────────────────────────────────────────────────
    # status values: shortlisted | applied_email | applied_link | skipped | no_email
    # Extended values used by pipeline: following_up | interview | offer
    status:         str = "shortlisted"
    pipeline_stage: str = "saved"   # saved | applied | following_up | interview | offer

    # ── Timestamps ──────────────────────────────────────────────────────────────
    scraped_at:  str = field(default_factory=lambda: datetime.now().isoformat())
    applied_at:  Optional[str] = None
    search_query: str = ""

    # ── Job metadata ────────────────────────────────────────────────────────────
    location:    str = ""
    date_posted: Optional[str] = None      # YYYY-MM-DD — used for freshness display
    expires_at:  Optional[str] = None      # ISO datetime — explicit expiry from source
    remote:      bool = False
    h1b_mention: bool = False

    # ── Salary ──────────────────────────────────────────────────────────────────
    salary_text: Optional[str] = None      # Human-readable: "$80,000 – $120,000/yr"
    salary_min:  Optional[float] = None    # Numeric min for filtering
    salary_max:  Optional[float] = None    # Numeric max for filtering

    # ── Multi-source apply links (JSearch only) ─────────────────────────────────
    # JSON array: [{"publisher": "LinkedIn", "link": "https://..."}, ...]
    # If the primary link is dead, the UI can offer these as fallbacks.
    apply_options: str = "[]"

    # ── Did-you-apply confirmation flow ─────────────────────────────────────────
    # apply_intent_at is set when the user clicks "Apply" in the dashboard.
    # apply_intent_acknowledged_at is set when the user answers Yes/No to the
    # "Did you apply?" modal. A new Apply click overrides apply_intent_at,
    # which makes the modal re-fire the next time the user returns.
    apply_intent_at:              Optional[str] = None
    apply_intent_acknowledged_at: Optional[str] = None
