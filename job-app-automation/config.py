import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR    = Path(__file__).parent
DATA_DIR    = BASE_DIR / "data"
UPLOADS_DIR = BASE_DIR / "uploads"
DB_PATH     = DATA_DIR / "jobs.db"

DATA_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)

# ── Tier 1: Primary job sources (best quality, US-focused, fresh data) ─────────

# JSearch via RapidAPI — real-time Google for Jobs (50+ boards in one call).
# Free tier: 200 requests/month. Get key: rapidapi.com → search "JSearch"
JSEARCH_API_KEY = os.getenv("JSEARCH_API_KEY", "")

# Adzuna — stable, documented, free API. 250 req/day free.
# Get key: developer.adzuna.com
ADZUNA_APP_ID  = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_API_KEY = os.getenv("ADZUNA_API_KEY", "")

# ── Tier 2: Supplemental sources (no cost, specific niches) ────────────────────

# USAJobs — official US federal government job board. Always-valid links.
# Free registration: developer.usajobs.gov/apirequest
USAJOBS_API_KEY    = os.getenv("USAJOBS_API_KEY", "")
USAJOBS_USER_AGENT = os.getenv("USAJOBS_USER_AGENT", "")  # must be your email

# The Muse — tech/creative roles. No key required.
# Remotive — remote-only roles. No key required.

# ── Tier 3: Optional free keys — add for more volume ───────────────────────────

# Findwork — tech/developer focused. Free key at findwork.dev
FINDWORK_API_KEY = os.getenv("FINDWORK_API_KEY", "")

# Jooble — large aggregator, broad US coverage. Free key at jooble.org/api/about
JOOBLE_API_KEY = os.getenv("JOOBLE_API_KEY", "")

# Careerjet — massive US aggregator, strong onsite + remote coverage.
# Free publisher key: https://www.careerjet.com/partners/register/as-publisher
CAREERJET_API_KEY = os.getenv("CAREERJET_API_KEY", "")

# ── AI matching ────────────────────────────────────────────────────────────────
DEFAULT_MATCH_THRESHOLD = 70
MIN_THRESHOLD           = 50
MAX_THRESHOLD           = 95
AI_MODEL_NAME           = "all-MiniLM-L6-v2"

# ── Local LLM (Ollama) — used by the resume bullet rewrite engine ──────────────
# The rewrite engine calls Ollama at OLLAMA_URL with OLLAMA_MODEL. If Ollama
# isn't running the engine falls back to deterministic templates so the app
# still works. Install Ollama (https://ollama.com) and run: ollama pull llama3.2:3b
OLLAMA_URL              = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL            = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_TIMEOUT_SECONDS  = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "20"))
OLLAMA_MAX_PARALLEL     = int(os.getenv("OLLAMA_MAX_PARALLEL", "4"))

# ── Search defaults ────────────────────────────────────────────────────────────
MAX_JOBS_PER_BOARD   = 20
SCRAPE_DELAY_SECONDS = 1

# ── Job expiry thresholds (days) ───────────────────────────────────────────────
# Jobs older than EXPIRY_WARN_DAYS get an orange "may be expiring" badge.
# Jobs older than EXPIRY_HIDE_DAYS are hidden unless user opts in.
EXPIRY_WARN_DAYS = 14
EXPIRY_HIDE_DAYS = 30

# ── Board display metadata ─────────────────────────────────────────────────────
# tier:        1 = primary (key required, best quality)
#              2 = free, no key needed
#              3 = optional free key
# remote_only: True = only returns remote listings (skip for city searches)
BOARD_DISPLAY = {
    # ── Tier 1: Primary — need a free key, best quality ────────────────────────
    "JSearch":   {"label": "JSearch",     "tag": "Tier 1 · Free key",  "color": "#4285f4", "tier": 1, "remote_only": False},
    "Adzuna":    {"label": "Adzuna",      "tag": "Tier 1 · Free key",  "color": "#0066cc", "tier": 1, "remote_only": False},

    # ── Tier 2: Zero setup — no key needed, work immediately ──────────────────
    "The Muse":  {"label": "The Muse",    "tag": "Tier 2 · No key",    "color": "#e91e8c", "tier": 2, "remote_only": False},
    "Arbeitnow": {"label": "Arbeitnow",   "tag": "Tier 2 · No key",    "color": "#6f42c1", "tier": 2, "remote_only": False},
    "RemoteOK":  {"label": "RemoteOK",    "tag": "Tier 2 · No key",    "color": "#17a2b8", "tier": 2, "remote_only": True},
    "Remotive":  {"label": "Remotive",    "tag": "Tier 2 · No key",    "color": "#20c997", "tier": 2, "remote_only": True},
    "Jobicy":    {"label": "Jobicy",      "tag": "Tier 2 · No key",    "color": "#fd7e14", "tier": 2, "remote_only": True},
    "Himalayas": {"label": "Himalayas",   "tag": "Tier 2 · No key",    "color": "#7c3aed", "tier": 2, "remote_only": True},

    # ── Tier 3: Optional — add free keys for more volume ──────────────────────
    "USAJobs":   {"label": "USAJobs",     "tag": "Tier 3 · Free key",  "color": "#0ea5e9", "tier": 3, "remote_only": False},
    "Findwork":  {"label": "Findwork",    "tag": "Tier 3 · Free key",  "color": "#e83e8c", "tier": 3, "remote_only": False},
    "Jooble":    {"label": "Jooble",      "tag": "Tier 3 · Free key",  "color": "#28a745", "tier": 3, "remote_only": False},
    "Careerjet": {"label": "Careerjet",   "tag": "Tier 3 · Free key",  "color": "#e25822", "tier": 3, "remote_only": False},
}

ADZUNA_COUNTRY_MAP = {
    "United States": "us",
    "United Kingdom": "gb",
    "Canada":        "ca",
    "Australia":     "au",
    "India":         "in",
    "Germany":       "de",
    "France":        "fr",
    "Netherlands":   "nl",
    "Singapore":     "sg",
}
