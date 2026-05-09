"""
Database layer for ResumeWing — all SQLite operations live here.

Design principles:
- Every public function is self-contained: opens its own connection,
  commits, and closes. No shared state between calls.
- _migrate_db() uses ALTER TABLE to add missing columns to existing databases
  so upgrades are automatic and non-destructive — users never lose their data.
- Row → dataclass conversion is centralised in _row_to_job() / _row_to_resume()
  so adding new fields only requires changes in one place.
"""
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from config import DB_PATH
from database.models import Job, Resume


# ── Connection ─────────────────────────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # WAL improves concurrent read performance
    return conn


# ── Schema initialisation & migration ─────────────────────────────────────────

def init_db() -> None:
    """
    Create all tables if they don't exist, then run the migration pass.
    Safe to call on every app startup — idempotent by design.
    """
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS resumes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                filename    TEXT NOT NULL,
                text        TEXT NOT NULL,
                skills      TEXT DEFAULT '[]',
                uploaded_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                title          TEXT NOT NULL,
                company        TEXT NOT NULL,
                description    TEXT NOT NULL,
                link           TEXT NOT NULL UNIQUE,
                contact_email  TEXT,
                source         TEXT NOT NULL,
                match_score    REAL DEFAULT 0.0,
                ats_score      REAL,
                status         TEXT DEFAULT 'shortlisted',
                scraped_at     TEXT NOT NULL,
                applied_at     TEXT,
                search_query   TEXT DEFAULT '',
                location       TEXT DEFAULT '',
                date_posted    TEXT,
                expires_at     TEXT,
                salary_text    TEXT,
                salary_min     REAL,
                salary_max     REAL,
                remote         INTEGER DEFAULT 0,
                h1b_mention    INTEGER DEFAULT 0,
                pipeline_stage TEXT DEFAULT 'saved',
                apply_options  TEXT DEFAULT '[]'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_profile (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.commit()
        _migrate_db(conn)


def _migrate_db(conn: sqlite3.Connection) -> None:
    """
    Non-destructive schema migration: add any missing columns to an existing
    jobs table. Existing data is never modified or deleted.

    This runs on every startup so users upgrading from older versions of
    ResumeWing automatically get the new columns without any manual steps.
    """
    cursor  = conn.cursor()
    existing = {row[1] for row in cursor.execute("PRAGMA table_info(jobs)")}

    # Column name → SQLite type definition.
    new_columns = {
        # v2 columns (may already exist on older installs)
        "date_posted":    "TEXT",
        "salary_text":    "TEXT",
        "remote":         "INTEGER DEFAULT 0",
        "h1b_mention":    "INTEGER DEFAULT 0",
        "pipeline_stage": "TEXT DEFAULT 'saved'",
        # v3 columns (new in this release)
        "expires_at":     "TEXT",
        "salary_min":     "REAL",
        "salary_max":     "REAL",
        "apply_options":  "TEXT DEFAULT '[]'",
        # v4 columns: did-you-apply confirmation flow
        "apply_intent_at":              "TEXT",
        "apply_intent_acknowledged_at": "TEXT",
        # v5 columns: per-job tailored resume text (ATS-score scratchpad)
        "tailored_resume_text":         "TEXT",
        "tailored_updated_at":          "TEXT",
    }
    for col, coldef in new_columns.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {coldef}")

    # Backfill pipeline_stage for old rows where it was never set.
    conn.execute("""
        UPDATE jobs SET pipeline_stage = CASE
            WHEN status IN ('applied_email', 'applied_link') THEN 'applied'
            WHEN status = 'following_up'                     THEN 'following_up'
            WHEN status = 'interview'                        THEN 'interview'
            WHEN status = 'offer'                            THEN 'offer'
            ELSE 'saved'
        END
        WHERE pipeline_stage IS NULL OR pipeline_stage = ''
    """)
    conn.commit()


# ── Resume operations ─────────────────────────────────────────────────────────

def save_resume(resume: Resume) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO resumes (filename, text, skills, uploaded_at) VALUES (?, ?, ?, ?)",
            (resume.filename, resume.text, resume.skills, resume.uploaded_at),
        )
        conn.commit()
        return cursor.lastrowid


def get_latest_resume() -> Optional[Resume]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM resumes ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return _row_to_resume(row) if row else None


def update_resume_skills(resume_id: int, skills_json: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE resumes SET skills = ? WHERE id = ?",
            (skills_json, resume_id),
        )
        conn.commit()


# ── Job operations ────────────────────────────────────────────────────────────

def save_job(job: Job) -> Optional[int]:
    """
    Insert a new job row. If the link already exists (UNIQUE constraint),
    returns the existing row's id instead of raising an error.
    Returns None only if the insert fails for an unexpected reason.
    """
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """INSERT INTO jobs (
                       title, company, description, link, contact_email, source,
                       match_score, ats_score, status, scraped_at, applied_at,
                       search_query, location, date_posted, expires_at,
                       salary_text, salary_min, salary_max,
                       remote, h1b_mention, pipeline_stage, apply_options
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job.title, job.company, job.description, job.link,
                    job.contact_email, job.source, job.match_score,
                    job.ats_score, job.status, job.scraped_at, job.applied_at,
                    job.search_query, job.location, job.date_posted,
                    job.expires_at, job.salary_text,
                    job.salary_min, job.salary_max,
                    int(job.remote), int(job.h1b_mention),
                    job.pipeline_stage, job.apply_options,
                ),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            # Link already exists — return the existing row's id.
            row = conn.execute(
                "SELECT id FROM jobs WHERE link = ?", (job.link,)
            ).fetchone()
            return row["id"] if row else None


def save_jobs(jobs: List[Job]) -> List[int]:
    """Batch save — returns list of row ids (new inserts + existing dupes)."""
    return [jid for job in jobs if (jid := save_job(job)) is not None]


def get_shortlisted_jobs(threshold: float = 0.0) -> List[Job]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM jobs
               WHERE status = 'shortlisted' AND match_score >= ?
               ORDER BY match_score DESC""",
            (threshold,),
        ).fetchall()
        return [_row_to_job(r) for r in rows]


def get_pipeline_jobs(stage: str) -> List[Job]:
    """Return all jobs in a given Kanban pipeline stage, excluding skipped."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM jobs
               WHERE pipeline_stage = ? AND status != 'skipped'
               ORDER BY match_score DESC""",
            (stage,),
        ).fetchall()
        return [_row_to_job(r) for r in rows]


def get_all_jobs() -> List[Job]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY scraped_at DESC"
        ).fetchall()
        return [_row_to_job(r) for r in rows]


def get_jobs_by_status(status: str) -> List[Job]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY scraped_at DESC",
            (status,),
        ).fetchall()
        return [_row_to_job(r) for r in rows]


def get_job_by_id(job_id: int) -> Optional[Job]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return _row_to_job(row) if row else None


def update_job_status(job_id: int, status: str) -> None:
    applied_at     = datetime.now().isoformat() if status.startswith("applied") else None
    pipeline_stage = _status_to_pipeline_stage(status)
    with get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, applied_at = ?, pipeline_stage = ? WHERE id = ?",
            (status, applied_at, pipeline_stage, job_id),
        )
        conn.commit()


def update_job_pipeline_stage(job_id: int, stage: str) -> None:
    """Move a job to a pipeline stage without changing its granular status."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET pipeline_stage = ? WHERE id = ?",
            (stage, job_id),
        )
        conn.commit()


def update_job_ats_score(job_id: int, ats_score: float) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET ats_score = ? WHERE id = ?", (ats_score, job_id)
        )
        conn.commit()


def update_job_match_score(job_id: int, match_score: float) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET match_score = ? WHERE id = ?",
            (match_score, job_id),
        )
        conn.commit()


def restore_job_to_shortlisted(job_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET status = 'shortlisted', applied_at = NULL, "
            "pipeline_stage = 'saved' WHERE id = ?",
            (job_id,),
        )
        conn.commit()


# ── Apply-intent tracking (did-you-apply confirmation flow) ─────────────────

def record_apply_intent(job_id: int) -> None:
    """
    Mark that the user clicked 'Apply' on this job. The dashboard will then
    ask "Did you apply?" the next time the user comes back to it.

    We update apply_intent_at regardless of whether a previous intent was
    acknowledged — this makes re-prompts work: every fresh Apply click
    creates a new pending intent.
    """
    with get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET apply_intent_at = ? WHERE id = ?",
            (datetime.now().isoformat(), job_id),
        )
        conn.commit()


def get_pending_apply_intents() -> List[Job]:
    """
    Return jobs where the user has clicked Apply but not yet answered
    "Did you apply?". Pending = intent is set AND (no acknowledgement, or
    intent is newer than the last acknowledgement — i.e. user clicked Apply
    again after answering No).
    """
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM jobs
               WHERE apply_intent_at IS NOT NULL
                 AND (apply_intent_acknowledged_at IS NULL
                      OR apply_intent_at > apply_intent_acknowledged_at)
               ORDER BY apply_intent_at DESC"""
        ).fetchall()
        return [_row_to_job(r) for r in rows]


def acknowledge_apply_intent(job_id: int, applied: bool) -> None:
    """
    User answered the 'Did you apply?' modal:
      applied=True  → mark the job as applied (status applied_link, pipeline applied)
      applied=False → just record the acknowledgement; job stays where it was
    Either way, the modal won't re-prompt for THIS click. A future Apply
    click will set a new apply_intent_at and re-trigger the modal.
    """
    now = datetime.now().isoformat()
    with get_connection() as conn:
        if applied:
            conn.execute(
                """UPDATE jobs
                   SET apply_intent_acknowledged_at = ?,
                       status        = 'applied_link',
                       applied_at    = ?,
                       pipeline_stage = 'applied'
                   WHERE id = ?""",
                (now, now, job_id),
            )
        else:
            conn.execute(
                "UPDATE jobs SET apply_intent_acknowledged_at = ? WHERE id = ?",
                (now, job_id),
            )
        conn.commit()


# ── Tailored resume text per job (Phase 3c) ──────────────────────────────────

def get_tailored_resume_text(job_id: int) -> Optional[str]:
    """Return the user's edited resume text for this job, or None if untouched."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT tailored_resume_text FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return row["tailored_resume_text"] if row and row["tailored_resume_text"] else None


def set_tailored_resume_text(job_id: int, text: str) -> None:
    """
    Save edited resume text for a specific job. Use case: the user iterates
    on keyword/phrasing changes for a particular role until the ATS score
    crosses the 80% threshold, without affecting the master resume.
    """
    with get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET tailored_resume_text = ?, tailored_updated_at = ? WHERE id = ?",
            (text, datetime.now().isoformat(), job_id),
        )
        conn.commit()


def clear_tailored_resume_text(job_id: int) -> None:
    """Discard the per-job tailored draft and revert to master resume for ATS scoring."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET tailored_resume_text = NULL, tailored_updated_at = NULL WHERE id = ?",
            (job_id,),
        )
        conn.commit()


def is_already_applied(job_id: int) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT status FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if row:
            return row["status"] in ("applied_email", "applied_link")
    return False


def search_jobs_db(query: str) -> List[Job]:
    """Full-text keyword search across title, company, and description."""
    q = f"%{query}%"
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM jobs
               WHERE title LIKE ? OR company LIKE ? OR description LIKE ?
               ORDER BY scraped_at DESC""",
            (q, q, q),
        ).fetchall()
        return [_row_to_job(r) for r in rows]


def clear_shortlisted_jobs() -> None:
    """Delete all saved/shortlisted jobs — used for 'Replace' search mode."""
    with get_connection() as conn:
        conn.execute("DELETE FROM jobs WHERE pipeline_stage = 'saved'")
        conn.commit()


def delete_job(job_id: int) -> None:
    """Permanently delete a single job by id."""
    with get_connection() as conn:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        conn.commit()


def clear_all_data(include_resume: bool = True) -> Dict[str, int]:
    """
    Nuclear reset: delete all jobs and, optionally, all stored resumes.
    Returns a count dict so the caller can confirm what was removed.
    """
    with get_connection() as conn:
        job_count = conn.execute("SELECT COUNT(*) AS c FROM jobs").fetchone()["c"]
        conn.execute("DELETE FROM jobs")
        resume_count = 0
        if include_resume:
            resume_count = conn.execute("SELECT COUNT(*) AS c FROM resumes").fetchone()["c"]
            conn.execute("DELETE FROM resumes")
        conn.commit()
    return {"jobs_deleted": job_count, "resumes_deleted": resume_count}


def get_stats() -> Dict[str, Any]:
    """Return aggregate counts used by the Dashboard stats bar."""
    with get_connection() as conn:
        def cnt(where: str = "", params: tuple = ()) -> int:
            q = "SELECT COUNT(*) as c FROM jobs"
            if where:
                q += " WHERE " + where
            return conn.execute(q, params).fetchone()["c"]

        return {
            "total":         cnt(),
            "shortlisted":   cnt("status = 'shortlisted'"),
            "applied_email": cnt("status = 'applied_email'"),
            "applied_link":  cnt("status = 'applied_link'"),
            "skipped":       cnt("status = 'skipped'"),
            "no_email":      cnt("status = 'no_email'"),
            "applied_total": cnt("status IN ('applied_email','applied_link')"),
            "following_up":  cnt("pipeline_stage = 'following_up'"),
            "interview":     cnt("pipeline_stage = 'interview'"),
            "offer":         cnt("pipeline_stage = 'offer'"),
            "h1b":           cnt("h1b_mention = 1"),
            "remote":        cnt("remote = 1"),
        }


# ── User profile (persistent settings) ───────────────────────────────────────

def get_profile(key: str, default: str = "") -> str:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM user_profile WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default


def set_profile(key: str, value: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO user_profile (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()


def get_all_profile() -> Dict[str, str]:
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM user_profile").fetchall()
        return {r["key"]: r["value"] for r in rows}


# ── Private helpers ───────────────────────────────────────────────────────────

def _status_to_pipeline_stage(status: str) -> str:
    return {
        "shortlisted":   "saved",
        "no_email":      "saved",
        "applied_email": "applied",
        "applied_link":  "applied",
        "following_up":  "following_up",
        "interview":     "interview",
        "offer":         "offer",
        "skipped":       "skipped",
    }.get(status, "saved")


def _row_to_job(row: sqlite3.Row) -> Job:
    """Convert a sqlite3.Row to a Job dataclass. Safe against missing columns."""
    cols = row.keys()

    def col(name: str, default=None):
        return row[name] if name in cols else default

    return Job(
        id            = row["id"],
        title         = row["title"],
        company       = row["company"],
        description   = row["description"],
        link          = row["link"],
        contact_email = row["contact_email"],
        source        = row["source"],
        match_score   = row["match_score"],
        ats_score     = row["ats_score"],
        status        = row["status"],
        scraped_at    = row["scraped_at"],
        applied_at    = row["applied_at"],
        search_query  = row["search_query"],
        location      = row["location"],
        date_posted   = col("date_posted"),
        expires_at    = col("expires_at"),
        salary_text   = col("salary_text"),
        salary_min    = col("salary_min"),
        salary_max    = col("salary_max"),
        remote        = bool(col("remote", 0)),
        h1b_mention   = bool(col("h1b_mention", 0)),
        pipeline_stage = col("pipeline_stage", "saved"),
        apply_options  = col("apply_options", "[]"),
        apply_intent_at              = col("apply_intent_at"),
        apply_intent_acknowledged_at = col("apply_intent_acknowledged_at"),
    )


def _row_to_resume(row: sqlite3.Row) -> Resume:
    return Resume(
        id          = row["id"],
        filename    = row["filename"],
        text        = row["text"],
        skills      = row["skills"],
        uploaded_at = row["uploaded_at"],
    )
