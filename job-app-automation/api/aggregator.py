"""
Aggregator — single entry point for all job search operations.

Responsibilities:
  1. Route the search to the correct enabled API clients.
  2. Fetch all boards IN PARALLEL using a thread pool — eliminates the
     sequential wait that caused 25+ second search times.
  3. Isolate failures — one board failing must not block others.
  4. Deduplicate across sources by both exact URL and title+company fingerprint.
  5. Sort final results by freshness (newest first).
  6. Emit progress messages via callback so the UI can show a live log.

Board inventory (12 total):
  Tier 1 — Primary (key required, best quality/volume):
    JSearch   — Google Jobs real-time via RapidAPI  (200 req/month free)
    Adzuna    — Broad US market, reliable links      (250 req/day free)

  Tier 2 — No key needed (zero setup):
    The Muse  — Tech/creative roles
    Remotive  — Remote-only roles
    RemoteOK  — Remote tech jobs
    Arbeitnow — Global tech + remote
    Jobicy    — US remote startups
    Himalayas — Remote startup/scale-up roles

  Tier 3 — Optional free key:
    USAJobs   — US federal government jobs
    Findwork  — Tech/developer focused
    Jooble    — High-volume global aggregator
    Careerjet — Massive US aggregator, onsite + remote (free publisher key)

The UI (ui/search.py) imports only search_all_sources() from this module.
Individual clients are never imported directly by the UI layer.
"""
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional, Tuple

from config import (
    ADZUNA_APP_ID, ADZUNA_API_KEY,
    CAREERJET_API_KEY,
    FINDWORK_API_KEY,
    JOOBLE_API_KEY,
    JSEARCH_API_KEY,
    USAJOBS_API_KEY, USAJOBS_USER_AGENT,
)
from database.models import Job


def _board_registry() -> Dict[str, Tuple]:
    """
    Build the board registry at call time so environment variables are always
    read from the current process state. This ensures keys saved via the
    Settings UI take effect after the next search without restarting.

    Returns a dict mapping board name → (fetch_function, is_configured, hint).
    """
    from api import (
        jsearch, adzuna, themuse, usajobs, remotive,
        remoteok, arbeitnow, jobicy, findwork, jooble, himalayas, careerjet,
    )

    return {
        # ── Tier 1 ──────────────────────────────────────────────────────────
        "JSearch": (
            jsearch.fetch,
            bool(JSEARCH_API_KEY),
            "Add JSEARCH_API_KEY — free key at rapidapi.com → search 'JSearch'",
        ),
        "Adzuna": (
            adzuna.fetch,
            bool(ADZUNA_APP_ID and ADZUNA_API_KEY),
            "Add ADZUNA_APP_ID + ADZUNA_API_KEY — free at developer.adzuna.com",
        ),

        # ── Tier 2: no key needed ────────────────────────────────────────────
        "The Muse": (
            themuse.fetch,
            True,
            "",
        ),
        "Remotive": (
            remotive.fetch,
            True,
            "",
        ),
        "RemoteOK": (
            remoteok.fetch,
            True,
            "",
        ),
        "Arbeitnow": (
            arbeitnow.fetch,
            True,
            "",
        ),
        "Jobicy": (
            jobicy.fetch,
            True,
            "",
        ),
        "Himalayas": (
            himalayas.fetch,
            True,
            "",
        ),

        # ── Tier 3: free key required ────────────────────────────────────────
        "USAJobs": (
            usajobs.fetch,
            bool(USAJOBS_API_KEY and USAJOBS_USER_AGENT),
            "Add USAJOBS_API_KEY + USAJOBS_USER_AGENT — free at developer.usajobs.gov",
        ),
        "Findwork": (
            findwork.fetch,
            bool(FINDWORK_API_KEY),
            "Add FINDWORK_API_KEY — free at findwork.dev",
        ),
        "Jooble": (
            jooble.fetch,
            bool(JOOBLE_API_KEY),
            "Add JOOBLE_API_KEY — free at jooble.org/api/about",
        ),
        "Careerjet": (
            careerjet.fetch,
            bool(CAREERJET_API_KEY),
            "Add CAREERJET_API_KEY — free at careerjet.com/partners/register/as-publisher",
        ),
    }


# Boards that are remote-only — skip for city/state location searches
# unless the user has explicitly enabled them.
_REMOTE_ONLY_BOARDS = {"RemoteOK", "Remotive", "Jobicy", "Himalayas"}


def search_all_sources(
    keywords: str,
    location: str,
    boards: List[str],
    num_per_board: int = 20,
    progress_callback: Optional[Callable[[str], None]] = None,
    date_filter: Optional[int] = None,
    job_type: Optional[str] = None,
) -> List[Job]:
    """
    Search all enabled boards IN PARALLEL and return a merged, deduplicated,
    freshness-sorted list of Job objects.

    All board fetches run concurrently in a thread pool.  The total wait time
    is now roughly the slowest single board (~3-5 s) rather than the sum of
    all boards (which could be 25+ s when searching 8+ sources).

    Args:
        keywords:          Job title or skill keywords.
        location:          US city/state string or "Remote".
        boards:            List of board names to query.
        num_per_board:     Max results to request from each board.
        progress_callback: Optional function for live log messages in the UI.
        date_filter:       Max job age in days (1, 3, 7, 30) or None for any.
        job_type:          Employment type filter string or None for any.

    Returns:
        Deduplicated Job list sorted by date_posted descending (newest first).
    """
    def log(msg: str) -> None:
        if progress_callback:
            progress_callback(msg)

    registry  = _board_registry()
    is_remote = location.lower().strip() in ("remote", "") or not location.strip()

    # Decide which boards to actually call and pre-log skipped ones.
    tasks: List[Tuple[str, Callable]] = []
    for board_name in boards:
        entry = registry.get(board_name)
        if not entry:
            log(f"⚠️  {board_name}: Unknown board — skipped")
            continue

        fetch_fn, is_configured, missing_hint = entry

        # Skip remote-only boards for city/state searches.
        if board_name in _REMOTE_ONLY_BOARDS and not is_remote:
            log(f"⏭  {board_name}: Skipped — remote-only board (location-specific search)")
            continue

        if not is_configured:
            log(f"⚠️  {board_name}: Not configured — {missing_hint}")
            continue

        tasks.append((board_name, fetch_fn))

    if not tasks:
        return []

    log(f"🚀 Searching {len(tasks)} board(s) in parallel…")

    # ── Parallel fetch ────────────────────────────────────────────────────────
    # Use a thread pool so I/O-bound network calls don't block each other.
    # Max workers capped at min(len(tasks), 8) to avoid overwhelming rate limits.
    board_results: Dict[str, List[Job]] = {}

    def _fetch_one(name: str, fn: Callable) -> Tuple[str, List[Job]]:
        return name, fn(
            keywords    = keywords,
            location    = location,
            num_results = num_per_board,
            date_filter = date_filter,
            job_type    = job_type,
        )

    with ThreadPoolExecutor(max_workers=min(len(tasks), 8)) as pool:
        futures = {pool.submit(_fetch_one, name, fn): name for name, fn in tasks}
        for future in as_completed(futures):
            board_name = futures[future]
            try:
                name, jobs = future.result()
                board_results[name] = jobs
                log(f"✅ {name}: {len(jobs)} jobs fetched")
            except RuntimeError as exc:
                log(f"❌ {board_name}: {exc}")
                board_results[board_name] = []
            except Exception as exc:
                log(f"❌ {board_name}: Unexpected error — {exc}")
                board_results[board_name] = []

    # ── Merge + deduplicate ───────────────────────────────────────────────────
    # Process boards in original order so Tier 1 boards' entries win on fingerprint ties.
    all_jobs: List[Job] = []
    seen_links: set = set()
    seen_fps:   set = set()

    for board_name, _ in tasks:
        jobs = board_results.get(board_name, [])
        new_jobs = _deduplicate_batch(jobs, seen_links, seen_fps)
        all_jobs.extend(new_jobs)
        if new_jobs:
            log(f"📌 {board_name}: {len(new_jobs)} unique added (of {len(jobs)} fetched)")
        else:
            log(f"⚪ {board_name}: No new unique jobs after dedup")

    # Sort: known dates first (newest to oldest), unknown dates at the end.
    all_jobs.sort(
        key=lambda j: j.date_posted or "0000-00-00",
        reverse=True,
    )

    log(f"🎯 Total: {len(all_jobs)} unique jobs from {len(tasks)} board(s)")
    return all_jobs


def get_board_status() -> Dict[str, dict]:
    """
    Return a dict of all boards with their configuration status.
    Used by the Settings and Search pages to show which boards are ready.

    Returns:
        {board_name: {"configured": bool, "hint": str, "remote_only": bool}}
    """
    registry = _board_registry()
    return {
        name: {
            "configured":  is_configured,
            "hint":        hint,
            "remote_only": name in _REMOTE_ONLY_BOARDS,
        }
        for name, (_, is_configured, hint) in registry.items()
    }


def _deduplicate_batch(
    jobs: List[Job],
    seen_links: set,
    seen_fps: set,
) -> List[Job]:
    """
    Remove duplicate jobs before adding to the aggregate pool.

    Two passes:
      Pass 1 — Exact URL: same posting URL from different sources.
      Pass 2 — Fingerprint: same role at same company listed on multiple boards
                            with different URLs (e.g. company page vs. LinkedIn).

    Modifies seen_links and seen_fps in-place so cross-board duplication
    is caught across multiple calls to this function.
    """
    unique: List[Job] = []
    for job in jobs:
        if job.link and job.link in seen_links:
            continue
        fp = _fingerprint(job.title, job.company)
        if fp in seen_fps:
            continue
        if job.link:
            seen_links.add(job.link)
        seen_fps.add(fp)
        unique.append(job)
    return unique


def _fingerprint(title: str, company: str) -> str:
    """
    Stable deduplication key from normalised title + company name.
    MD5 is fast and sufficient — this is not a security-sensitive operation.
    """
    normalised = f"{title.lower().strip()}|{company.lower().strip()}"
    return hashlib.md5(normalised.encode()).hexdigest()
