"""
ResumeWing — Daily Digest Email
================================
Runs once a day (via Windows Task Scheduler / cron on macOS / Linux), searches
the configured keywords + location across every configured job board, ranks
results against the user's latest resume using the existing AI matcher, and
emails the top N matches to DIGEST_EMAIL_TO using SMTP with a Gmail App
Password.

Design goals:
    1. Zero new runtime dependencies. Uses stdlib smtplib + email + json.
       No FastAPI server needs to be running; this script imports the
       aggregator / scorer / db modules directly.
    2. Idempotent and crash-safe. Every failure mode either logs and exits
       cleanly, or falls back to a still-useful result. Never partial state.
    3. No repeats. A persisted state file (data/digest_state.json) remembers
       which job URLs have been emailed so the digest never spams the same
       posting twice. Entries are auto-pruned after DIGEST_STATE_TTL_DAYS.
    4. Reuses existing scoring + dedup logic — no duplication of business
       rules between the dashboard and the digest.

Run manually:
    cd job-app-automation
    venv\\Scripts\\python digest_email.py

Run automatically (Windows):
    schtasks /Create /TN ResumeWingDigest /TR "...\\run_digest.bat" ^
             /SC DAILY /ST 08:00 /F

Exit codes:
    0 — Digest sent (or "no matches" notice sent).
    1 — Disabled by config (no DIGEST_EMAIL_TO set) — not an error.
    2 — Required config missing or invalid (e.g. password placeholder).
    3 — No resume uploaded yet, nothing to score against.
    4 — SMTP failure (auth, connection, or send error).
    5 — Unexpected error during search or scoring.
"""
from __future__ import annotations

import json
import logging
import smtplib
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from html import escape as _esc
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Importing config also calls load_dotenv() — keep this near the top so every
# DIGEST_* variable in the .env file is read before we touch them.
import config
from database.db import (
    get_latest_resume,
    get_pipeline_jobs,
    init_db,
    save_job,
)
from database.models import Job


# ── Constants ──────────────────────────────────────────────────────────────────

DIGEST_STATE_PATH    = config.DATA_DIR / "digest_state.json"
DIGEST_LOG_PATH      = config.DATA_DIR / "digest.log"
DIGEST_STATE_TTL_DAYS = 60      # auto-prune URLs we emailed >60 days ago
MAX_KEYWORDS         = 5        # cap to avoid burning JSearch's 200/month quota
SMTP_TIMEOUT_SECONDS = 30
DESCRIPTION_PREVIEW_CHARS = 260

# Password placeholders we should refuse to send with
_PLACEHOLDER_PASSWORDS: Set[str] = {
    "", "xxxx xxxx xxxx xxxx", "xxxxxxxxxxxxxxxx",
    "your-app-password-here", "your-gmail-app-password",
}


# ── Logging setup ──────────────────────────────────────────────────────────────

def _setup_logging() -> logging.Logger:
    """File + stdout logging. Task Scheduler captures stdout; file is for diff."""
    # Force UTF-8 on stdout so em-dashes / arrows / non-ASCII in log messages
    # render correctly in PowerShell + cmd (default cp1252 mangles them to '?').
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    logger = logging.getLogger("digest")
    logger.setLevel(logging.INFO)
    # Avoid duplicate handlers if called twice in the same process
    if logger.handlers:
        return logger

    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s")

    try:
        DIGEST_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        file_h = logging.FileHandler(DIGEST_LOG_PATH, encoding="utf-8")
        file_h.setFormatter(fmt)
        logger.addHandler(file_h)
    except OSError:
        # If we can't write the log file, fall back to stdout-only logging.
        pass

    stream_h = logging.StreamHandler(sys.stdout)
    stream_h.setFormatter(fmt)
    logger.addHandler(stream_h)

    return logger


log = _setup_logging()


# ── Config dataclass ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DigestConfig:
    email_to:       str
    smtp_host:      str
    smtp_port:      int
    smtp_user:      str
    smtp_password:  str
    keywords:       Tuple[str, ...]
    locations:      Tuple[str, ...]   # 1+ comma-separated values (e.g. "United States", "Remote")
    top_n:          int
    num_per_board:  int
    max_age_days:   int
    dashboard_url:  str


def _load_config() -> Optional[DigestConfig]:
    """
    Pull DIGEST_* values out of the already-loaded config module.
    Returns None if the feature is effectively disabled (no recipient).
    Raises ValueError if it's partially configured (some fields set, others not).
    """
    recipient = (config.DIGEST_EMAIL_TO or "").strip()
    if not recipient:
        return None

    smtp_user     = (config.DIGEST_SMTP_USER or "").strip()
    smtp_password = (config.DIGEST_SMTP_PASSWORD or "").strip()
    keywords_raw  = (config.DIGEST_KEYWORDS or "").strip()
    locations_raw = (config.DIGEST_LOCATION or "").strip()

    missing: List[str] = []
    if not smtp_user:
        missing.append("DIGEST_SMTP_USER")
    if not smtp_password:
        missing.append("DIGEST_SMTP_PASSWORD")
    if not keywords_raw:
        missing.append("DIGEST_KEYWORDS")
    if missing:
        raise ValueError(
            "DIGEST_EMAIL_TO is set but these required values are missing: "
            + ", ".join(missing)
        )

    if smtp_password.lower() in _PLACEHOLDER_PASSWORDS:
        raise ValueError(
            "DIGEST_SMTP_PASSWORD looks like a placeholder. Generate a Gmail "
            "App Password at https://myaccount.google.com/apppasswords and "
            "paste the 16-character string into your .env file."
        )

    # Split + trim keywords, drop empties, cap at MAX_KEYWORDS to keep the
    # JSearch monthly quota safe (200 calls/month).
    keywords = tuple(
        k.strip() for k in keywords_raw.split(",") if k.strip()
    )
    if not keywords:
        raise ValueError("DIGEST_KEYWORDS contained no usable terms after parsing.")
    if len(keywords) > MAX_KEYWORDS:
        log.warning(
            "DIGEST_KEYWORDS has %d entries; only the first %d will be used "
            "(JSearch monthly quota protection).",
            len(keywords), MAX_KEYWORDS,
        )
        keywords = keywords[:MAX_KEYWORDS]

    # DIGEST_LOCATION can be a single value ("United States") or a comma-
    # separated list ("United States,Remote"). Each value triggers its own
    # search cycle; results are deduped by URL across all cycles.
    # An empty value is treated as a single "Remote" cycle.
    locations = tuple(l.strip() for l in locations_raw.split(",") if l.strip())
    if not locations:
        locations = ("Remote",)

    return DigestConfig(
        email_to      = recipient,
        smtp_host     = config.DIGEST_SMTP_HOST or "smtp.gmail.com",
        smtp_port     = int(config.DIGEST_SMTP_PORT or 587),
        smtp_user     = smtp_user,
        smtp_password = smtp_password,
        keywords      = keywords,
        locations     = locations,
        top_n         = max(1, int(config.DIGEST_TOP_N or 5)),
        num_per_board = max(1, int(config.DIGEST_NUM_PER_BOARD or 10)),
        max_age_days  = max(1, int(config.DIGEST_MAX_AGE_DAYS or 7)),
        dashboard_url = (config.DIGEST_DASHBOARD_URL or "http://localhost:3000").rstrip("/"),
    )


# ── Sent-state persistence (so we never email the same job twice) ─────────────

def _load_sent_state() -> Dict[str, str]:
    """Load the URL→ISO-timestamp map of jobs we've already emailed."""
    try:
        if DIGEST_STATE_PATH.exists():
            with DIGEST_STATE_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return {str(k): str(v) for k, v in data.items()}
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Could not read digest_state.json (%s) — treating as empty.", exc)
    return {}


def _save_sent_state(state: Dict[str, str]) -> None:
    """Persist the URL→timestamp map. Best-effort — never raises."""
    try:
        DIGEST_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = DIGEST_STATE_PATH.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, sort_keys=True)
        tmp.replace(DIGEST_STATE_PATH)
    except OSError as exc:
        log.warning("Could not write digest_state.json (%s).", exc)


def _prune_sent_state(state: Dict[str, str]) -> Dict[str, str]:
    """Drop entries older than DIGEST_STATE_TTL_DAYS so the file stays small."""
    cutoff = datetime.now() - timedelta(days=DIGEST_STATE_TTL_DAYS)
    pruned: Dict[str, str] = {}
    for url, ts in state.items():
        try:
            if datetime.fromisoformat(ts) >= cutoff:
                pruned[url] = ts
        except ValueError:
            # Bad timestamp — keep the entry for safety (the goal is to not
            # re-email; a corrupt date shouldn't undo that protection).
            pruned[url] = ts
    if len(pruned) < len(state):
        log.info("Pruned %d stale digest_state entries.", len(state) - len(pruned))
    return pruned


# ── Search + ranking ───────────────────────────────────────────────────────────

def _board_names_to_query() -> Tuple[List[str], List[str]]:
    """
    Partition the configured boards into (location_boards, remote_only_boards).

    The aggregator's search_all_sources() internally skips remote-only boards
    when given a city/state/country, so to cover all 12 boards we need to call
    it twice: once with the user's location for the location-boards and once
    with "Remote" for the remote-only boards.
    """
    from api.aggregator import get_board_status
    status = get_board_status()
    location_boards: List[str] = []
    remote_only_boards: List[str] = []
    for name, info in status.items():
        if not info["configured"]:
            continue
        if info["remote_only"]:
            remote_only_boards.append(name)
        else:
            location_boards.append(name)
    return location_boards, remote_only_boards


def _passes_for_location(
    user_loc: str,
    location_boards: List[str],
    remote_only_boards: List[str],
) -> List[Tuple[str, str, List[str]]]:
    """
    Return the (label, location_arg, board_list) tuples needed to cover every
    configured board for a single user-supplied location value.

    A specific city/country needs two passes: the location itself for the
    "city-aware" boards, and "Remote" for the four remote-only boards (which
    the aggregator otherwise skips when given a non-remote location).

    "Remote" by itself only needs one pass — every board can be queried with
    "Remote" directly.
    """
    loc_is_remote = user_loc.lower().strip() in ("remote", "") or not user_loc.strip()
    passes: List[Tuple[str, str, List[str]]] = []
    if loc_is_remote:
        all_boards = location_boards + remote_only_boards
        if all_boards:
            passes.append(("Remote", "Remote", all_boards))
    else:
        if location_boards:
            passes.append((user_loc, user_loc, location_boards))
        if remote_only_boards:
            passes.append((f"Remote (for remote-only boards, while location={user_loc!r})",
                           "Remote", remote_only_boards))
    return passes


def _aggregate_search(cfg: DigestConfig) -> List[Job]:
    """
    For each keyword × each value in cfg.locations, run the appropriate
    pass(es) so every configured board gets queried. Results are deduped by
    URL across keywords, locations, and passes.

    Quota note: if you set DIGEST_LOCATION to N comma-separated values,
    JSearch (200 req/month free tier) gets ~N calls per keyword per day.
    With 5 keywords × 2 locations × 30 days = 300/month — over the limit.
    Either keep keywords + locations ≤ ~3 each, or accept JSearch rate-limiting
    later in the month (the script will log + continue with the other boards).
    """
    from api.aggregator import search_all_sources

    location_boards, remote_only_boards = _board_names_to_query()
    if not (location_boards or remote_only_boards):
        log.warning("No job boards are configured. Add free keys in .env to enable digests.")
        return []

    total_unique_boards = len(location_boards) + len(remote_only_boards)
    log.info(
        "Querying %d configured board(s) for %d keyword(s) across %d location(s): %s",
        total_unique_boards, len(cfg.keywords), len(cfg.locations), list(cfg.locations),
    )

    merged: List[Job] = []
    seen_urls: Set[str] = set()

    for kw in cfg.keywords:
        for loc in cfg.locations:
            for label, pass_location, pass_boards in _passes_for_location(
                loc, location_boards, remote_only_boards
            ):
                log.info(
                    "  Search: keyword=%r location=%r pass=%r boards=%d",
                    kw, loc, label, len(pass_boards),
                )
                try:
                    jobs = search_all_sources(
                        keywords      = kw,
                        location      = pass_location,
                        boards        = pass_boards,
                        num_per_board = cfg.num_per_board,
                        date_filter   = cfg.max_age_days,
                        job_type      = None,
                    )
                except Exception as exc:
                    log.warning("    Aggregator raised: %s - skipping this pass.", exc)
                    continue

                new_count = 0
                for job in jobs:
                    if not job.link or job.link in seen_urls:
                        continue
                    seen_urls.add(job.link)
                    # Stamp the search_query so the dashboard shows provenance.
                    job.search_query = kw
                    merged.append(job)
                    new_count += 1
                log.info("    + %d new (of %d returned)", new_count, len(jobs))

                # Small breather so we don't burst free-tier rate limits.
                time.sleep(0.5)

    log.info("Merged %d unique jobs across all keywords / locations.", len(merged))
    return merged


def _exclude_already_actioned(jobs: List[Job], sent_urls: Set[str]) -> List[Job]:
    """
    Filter out jobs that:
      - have already been emailed in a previous digest (sent_urls), OR
      - the user has already applied to / skipped (DB status).
    """
    # Build the "already touched" URL set from DB pipeline stages
    actioned_urls: Set[str] = set()
    for stage in ("applied", "following_up", "interview", "offer", "skipped"):
        for j in get_pipeline_jobs(stage):
            if j.link:
                actioned_urls.add(j.link)

    # Some DB rows may use status without pipeline_stage — catch those too
    try:
        from database.db import get_jobs_by_status
        for s in ("applied_email", "applied_link", "skipped"):
            for j in get_jobs_by_status(s):
                if j.link:
                    actioned_urls.add(j.link)
    except Exception:
        pass

    kept = [
        j for j in jobs
        if j.link and j.link not in sent_urls and j.link not in actioned_urls
    ]
    excluded = len(jobs) - len(kept)
    if excluded:
        log.info("Excluded %d job(s) already applied/skipped/previously emailed.", excluded)
    return kept


def _rank_and_save(
    jobs: List[Job],
    resume_text: str,
    keywords_label: str,
) -> List[Tuple[Job, float]]:
    """
    Score every job against the resume with the same batched scorer used by
    /jobs/search-and-save, then persist them as "shortlisted" so the user can
    see them in the dashboard. Returns [(job, match_score)] sorted desc.
    """
    from matching.scorer import score_jobs_batch

    if not jobs:
        return []
    if not resume_text:
        return [(j, 0.0) for j in jobs]

    try:
        scored = score_jobs_batch(resume_text=resume_text, jobs=jobs)
    except Exception as exc:
        log.warning("Batch scoring failed (%s); falling back to date sort.", exc)
        scored = [(j, 0.0) for j in jobs]

    # Persist each job. save_job is idempotent — if the URL already exists it
    # returns the existing row's id. We assign back so the dashboard link can
    # carry a stable id, but a missing id is non-fatal.
    saved: List[Tuple[Job, float]] = []
    for job, score in scored:
        job.match_score    = round(float(score), 1)
        job.search_query   = job.search_query or keywords_label
        job.status         = "shortlisted"
        job.pipeline_stage = "saved"
        try:
            row_id = save_job(job)
            if row_id is not None:
                job.id = row_id
        except Exception as exc:
            log.debug("save_job failed for %s: %s — including anyway.", job.link, exc)
        saved.append((job, job.match_score))

    saved.sort(key=lambda t: t[1], reverse=True)
    return saved


# ── HTML + plain-text email rendering ─────────────────────────────────────────

def _strip_html_quick(s: str) -> str:
    """Drop HTML tags + collapse whitespace. Good enough for a preview snippet."""
    if not s:
        return ""
    import re as _re
    s = _re.sub(r"<[^>]+>", " ", s)
    try:
        import html as _html
        s = _html.unescape(s)
    except Exception:
        pass
    s = _re.sub(r"\s+", " ", s).strip()
    return s


def _score_color(score: float) -> str:
    """Match the dashboard's colour scale so the emailed score looks familiar."""
    if score >= 80:
        return "#16a34a"   # green
    if score >= 65:
        return "#0ea5e9"   # blue
    if score >= 50:
        return "#f59e0b"   # amber
    return "#94a3b8"       # slate-grey


def _dashboard_link(cfg: DigestConfig, job: Job) -> str:
    """
    Link the user back to the dashboard so they can see ATS scoring + refine
    the resume for this job. Plain `/dashboard` works guaranteed; if a focus
    deep-link param is added to the dashboard later, this is the single place
    to update.
    """
    return f"{cfg.dashboard_url}/dashboard"


def _render_html(cfg: DigestConfig, picks: List[Tuple[Job, float]], now: datetime) -> str:
    pretty_date = now.strftime("%A, %B %d, %Y")
    count = len(picks)
    keywords_pretty = ", ".join(cfg.keywords)
    loc_pretty = ", ".join(cfg.locations) if cfg.locations else "Anywhere"

    job_blocks: List[str] = []
    for job, score in picks:
        title    = _esc(job.title or "Untitled role")
        company  = _esc(job.company or "Unknown company")
        location = _esc(job.location or ("Remote" if job.remote else "—"))
        source   = _esc(job.source or "")
        salary   = _esc(job.salary_text or "")
        apply_url = _esc(job.link or cfg.dashboard_url)
        dash_url  = _esc(_dashboard_link(cfg, job))
        preview  = _esc(_strip_html_quick(job.description)[:DESCRIPTION_PREVIEW_CHARS])
        if preview and len(_strip_html_quick(job.description)) > DESCRIPTION_PREVIEW_CHARS:
            preview += "…"
        score_color = _score_color(score)
        score_label = f"{score:.0f}% match"

        salary_row = (
            f'<div style="color:#475569;font-size:13px;margin-top:6px;">💰 {salary}</div>'
            if salary else ""
        )

        job_blocks.append(f"""
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%"
               style="border:1px solid #e2e8f0;border-radius:12px;margin:0 0 16px 0;background:#ffffff;">
            <tr><td style="padding:18px 20px 16px 20px;">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">
                    <div style="flex:1;">
                        <a href="{apply_url}" style="font-size:17px;font-weight:600;color:#0f172a;text-decoration:none;">
                            {title}
                        </a>
                        <div style="color:#334155;font-size:14px;margin-top:4px;">
                            {company} · {location}
                            {f' · <span style="color:#64748b;">{source}</span>' if source else ''}
                        </div>
                    </div>
                    <div style="white-space:nowrap;background:{score_color};color:#ffffff;
                                font-size:12px;font-weight:600;padding:6px 10px;border-radius:999px;">
                        {score_label}
                    </div>
                </div>
                {salary_row}
                <div style="color:#475569;font-size:13px;line-height:1.5;margin-top:10px;">
                    {preview}
                </div>
                <div style="margin-top:14px;">
                    <a href="{apply_url}"
                       style="display:inline-block;background:#0f172a;color:#ffffff;text-decoration:none;
                              font-size:13px;font-weight:600;padding:9px 16px;border-radius:8px;
                              margin-right:8px;">
                        View &amp; Apply
                    </a>
                    <a href="{dash_url}"
                       style="display:inline-block;color:#0f172a;text-decoration:none;
                              font-size:13px;font-weight:500;padding:9px 14px;border:1px solid #cbd5e1;
                              border-radius:8px;">
                        Open in dashboard
                    </a>
                </div>
            </td></tr>
        </table>
        """)

    body_jobs = "\n".join(job_blocks) if job_blocks else f"""
        <div style="padding:24px;border:1px dashed #cbd5e1;border-radius:12px;
                    background:#f8fafc;color:#475569;font-size:14px;text-align:center;">
            No new strong matches today. Try widening your keywords or location
            in <code>.env</code>, or check the dashboard for older saves:
            <br/><a href="{_esc(cfg.dashboard_url)}/dashboard"
                    style="color:#0f172a;font-weight:600;">Open dashboard →</a>
        </div>
    """

    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#0f172a;">
  <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background:#f1f5f9;">
    <tr><td align="center" style="padding:32px 16px;">
      <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="640" style="max-width:640px;">
        <tr><td style="padding-bottom:8px;">
          <div style="font-size:13px;color:#64748b;letter-spacing:0.04em;text-transform:uppercase;">
            ResumeWing · Daily Digest
          </div>
          <h1 style="margin:6px 0 0 0;font-size:22px;color:#0f172a;">
            {count} job{'s' if count != 1 else ''} ranked for you — {_esc(pretty_date)}
          </h1>
          <div style="margin:6px 0 22px 0;font-size:13px;color:#475569;">
            Search: <strong>{_esc(keywords_pretty)}</strong>  ·  Location: <strong>{_esc(loc_pretty)}</strong>
          </div>
        </td></tr>
        <tr><td>
          {body_jobs}
        </td></tr>
        <tr><td style="padding-top:18px;font-size:12px;color:#64748b;line-height:1.6;">
          Ranked against your latest resume using the same scorer that powers the
          dashboard. Already-applied and previously-emailed roles are filtered out.
          <br/>
          To stop these emails, comment out <code>DIGEST_EMAIL_TO</code> in
          <code>.env</code> or remove the scheduled task in Task Scheduler.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def _render_plain(cfg: DigestConfig, picks: List[Tuple[Job, float]], now: datetime) -> str:
    """Plain-text fallback for mail clients that strip HTML."""
    pretty_date = now.strftime("%A, %B %d, %Y")
    lines: List[str] = [
        f"ResumeWing — Daily Digest",
        f"{pretty_date}",
        f"Search: {', '.join(cfg.keywords)}",
        f"Location: {', '.join(cfg.locations) if cfg.locations else 'Anywhere'}",
        "",
    ]
    if not picks:
        lines.append("No new strong matches today.")
        lines.append(f"Open dashboard: {cfg.dashboard_url}/dashboard")
        return "\n".join(lines)

    for i, (job, score) in enumerate(picks, start=1):
        lines.append(f"{i}. {job.title or 'Untitled role'}  —  {score:.0f}% match")
        lines.append(f"   {job.company or 'Unknown company'} · {job.location or 'Remote'}"
                     + (f" · {job.source}" if job.source else ""))
        if job.salary_text:
            lines.append(f"   {job.salary_text}")
        preview = _strip_html_quick(job.description)[:220]
        if preview:
            lines.append(f"   {preview}…" if len(_strip_html_quick(job.description)) > 220 else f"   {preview}")
        lines.append(f"   Apply:     {job.link}")
        lines.append(f"   Dashboard: {_dashboard_link(cfg, job)}")
        lines.append("")
    lines.append("— ResumeWing")
    return "\n".join(lines)


# ── SMTP send ──────────────────────────────────────────────────────────────────

def _send_email(
    cfg: DigestConfig,
    subject: str,
    html_body: str,
    plain_body: str,
) -> None:
    """
    Send a multipart/alternative email via STARTTLS. Raises on any SMTP error
    so the caller can map it to a non-zero exit code (Task Scheduler then shows
    the run as failed).
    """
    msg = EmailMessage()
    msg["Subject"]    = subject
    msg["From"]       = formataddr(("ResumeWing Digest", cfg.smtp_user))
    msg["To"]         = cfg.email_to
    msg["Message-ID"] = make_msgid(domain="resumewing.local")
    msg.set_content(plain_body, subtype="plain", charset="utf-8")
    msg.add_alternative(html_body, subtype="html")

    log.info("Connecting to SMTP %s:%d …", cfg.smtp_host, cfg.smtp_port)
    with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=SMTP_TIMEOUT_SECONDS) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(cfg.smtp_user, cfg.smtp_password)
        server.send_message(msg)
    log.info("Email sent to %s.", cfg.email_to)


# ── Main pipeline ──────────────────────────────────────────────────────────────

def main() -> int:
    log.info("=" * 60)
    log.info("ResumeWing digest run starting.")

    # Make sure the DB exists even on a brand-new install.
    try:
        init_db()
    except Exception as exc:
        log.warning("init_db raised (%s) — continuing; DB may already be fine.", exc)

    # ── Config ───────────────────────────────────────────────────────────────
    try:
        cfg = _load_config()
    except ValueError as exc:
        log.error("Digest config error: %s", exc)
        return 2

    if cfg is None:
        log.info("DIGEST_EMAIL_TO is empty — digest feature disabled. Exiting.")
        return 1

    log.info(
        "Config OK: to=%s, smtp=%s:%d, sender=%s, keywords=%s, locations=%s, "
        "top_n=%d, num_per_board=%d, max_age_days=%d",
        cfg.email_to, cfg.smtp_host, cfg.smtp_port, cfg.smtp_user,
        list(cfg.keywords), list(cfg.locations),
        cfg.top_n, cfg.num_per_board, cfg.max_age_days,
    )

    # ── Resume ───────────────────────────────────────────────────────────────
    resume = get_latest_resume()
    if not resume or not (resume.text or "").strip():
        log.error("No resume uploaded yet. Upload a resume in the dashboard first.")
        return 3
    log.info("Using resume: %s (%d chars).", resume.filename, len(resume.text))

    # ── Search ───────────────────────────────────────────────────────────────
    try:
        candidates = _aggregate_search(cfg)
    except Exception as exc:
        log.exception("Unexpected error during search: %s", exc)
        return 5

    sent_state = _prune_sent_state(_load_sent_state())
    sent_urls  = set(sent_state.keys())

    fresh = _exclude_already_actioned(candidates, sent_urls)

    # ── Rank + save ──────────────────────────────────────────────────────────
    try:
        ranked = _rank_and_save(
            jobs=fresh,
            resume_text=resume.text,
            keywords_label=", ".join(cfg.keywords),
        )
    except Exception as exc:
        log.exception("Unexpected error during scoring: %s", exc)
        return 5

    picks = ranked[: cfg.top_n]
    log.info(
        "Selected top %d of %d ranked (overall pool: %d after filtering).",
        len(picks), len(ranked), len(fresh),
    )

    # ── Render + send ────────────────────────────────────────────────────────
    now = datetime.now()
    if picks:
        subject = (
            f"ResumeWing — {len(picks)} job match{'es' if len(picks) != 1 else ''} "
            f"for {now.strftime('%b %d')}"
        )
    else:
        subject = f"ResumeWing — no new matches for {now.strftime('%b %d')}"

    html_body  = _render_html(cfg, picks, now)
    plain_body = _render_plain(cfg, picks, now)

    try:
        _send_email(cfg, subject, html_body, plain_body)
    except smtplib.SMTPAuthenticationError as exc:
        log.error(
            "SMTP authentication failed: %s. Verify DIGEST_SMTP_USER and that "
            "DIGEST_SMTP_PASSWORD is a fresh Gmail App Password (not your normal "
            "account password) generated at https://myaccount.google.com/apppasswords",
            exc,
        )
        return 4
    except (smtplib.SMTPException, OSError) as exc:
        log.exception("SMTP send failed: %s", exc)
        return 4

    # ── Persist sent state ───────────────────────────────────────────────────
    ts_now = now.isoformat()
    for job, _ in picks:
        if job.link:
            sent_state[job.link] = ts_now
    _save_sent_state(sent_state)

    log.info("Digest run complete. %d jobs emailed.", len(picks))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log.warning("Interrupted by user.")
        sys.exit(130)
    except Exception as exc:    # safety net — never crash silently
        log.exception("Fatal unhandled error: %s", exc)
        sys.exit(5)
