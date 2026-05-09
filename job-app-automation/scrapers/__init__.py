"""
Unified scraper interface.
Calls all enabled boards and merges results, deduplicating by link.

date_filter : None = any time, 1 = 24 h, 3 = 3 days, 7 = 1 week, 30 = 1 month
job_type    : None / "Full-time" / "Part-time" / "Contract" / "Remote" / "Internship"
"""
from typing import List, Callable, Optional

from database.models import Job
from config import ADZUNA_APP_ID, ADZUNA_API_KEY, FINDWORK_API_KEY, JOOBLE_API_KEY


def scrape_all(
    keywords: str,
    location: str,
    boards: List[str],
    num_per_board: int = 20,
    progress_callback: Callable[[str], None] = None,
    date_filter: Optional[int] = None,
    job_type: Optional[str] = None,
) -> List[Job]:
    """
    Scrape enabled boards and return merged, deduplicated Job list.
    Each board failure is fully isolated — others continue regardless.
    """
    from scrapers import adzuna, remoteok, remotive, arbeitnow, jobicy, findwork, jooble

    board_map = {
        "Adzuna":    adzuna.scrape,
        "RemoteOK":  remoteok.scrape,
        "Remotive":  remotive.scrape,
        "Arbeitnow": arbeitnow.scrape,
        "Jobicy":    jobicy.scrape,
        "Findwork":  findwork.scrape,
        "Jooble":    jooble.scrape,
    }

    # Pre-flight checks
    skip_reasons = {}
    if "Adzuna" in boards and not (ADZUNA_APP_ID and ADZUNA_API_KEY):
        skip_reasons["Adzuna"] = "API credentials not configured (add in Settings)"
    if "Findwork" in boards and not FINDWORK_API_KEY:
        skip_reasons["Findwork"] = "API key not configured (add in Settings)"
    if "Jooble" in boards and not JOOBLE_API_KEY:
        skip_reasons["Jooble"] = "API key not configured (add in Settings)"

    all_jobs: List[Job] = []
    seen_links: set = set()

    for board_name in boards:
        fn = board_map.get(board_name)
        if not fn:
            continue

        if board_name in skip_reasons:
            if progress_callback:
                progress_callback(f"⚠️ {board_name}: {skip_reasons[board_name]} — skipped")
            continue

        if progress_callback:
            progress_callback(f"Searching {board_name}...")

        try:
            jobs = fn(
                keywords,
                location,
                num_per_board,
                date_filter=date_filter,
                job_type=job_type,
            )
            new = [j for j in jobs if j.link and j.link not in seen_links]
            for j in new:
                seen_links.add(j.link)
            all_jobs.extend(new)
            if progress_callback:
                progress_callback(f"✓ {board_name}: {len(new)} jobs found")
        except Exception as exc:
            if progress_callback:
                progress_callback(f"✗ {board_name}: {exc}")

    return all_jobs
