# ResumeWing — The Free, Open-Source Job Application Toolkit

> Find jobs faster, tailor your resume smarter, track your pipeline, and land interviews — all from your local machine, all for free.

---

## What It Does

| Feature | Description |
|---|---|
| **12 Job Boards** | JSearch, Adzuna, The Muse, RemoteOK, Remotive, Arbeitnow, Jobicy, Himalayas, USAJobs, Findwork, Jooble, Careerjet |
| **AI Matching** | Local sentence-transformers model — 0–100% relevance score per job |
| **Date Filters** | Last 24h / 3 days / 1 week / 1 month across all boards |
| **H1B Filter** | Highlights jobs that mention visa sponsorship in the description |
| **Salary Display** | Shows salary range when available from the source |
| **ATS Scanner** | KeyBERT keyword extraction + semantic similarity + LLM bullet rewrites |
| **AI Summary Rewrite** | Local Ollama tailors your professional summary per job (no fabrication) |
| **Kanban Pipeline** | Saved → Applied → Following Up → Interview → Offer |
| **"Did you apply?" Modal** | Confirms each application after clicking Apply (never auto-marks) |
| **Browser Extension** | Auto-fills forms on Greenhouse, Lever, Workday, Ashby, SmartRecruiters + universal fallback |
| **History & Export** | Full log, filterable by source, status, H1B, remote |
| **Profile Persistence** | Name, email, preferences saved to local SQLite — survive restarts |

**Total monthly cost: $0.00** (Ollama runs locally; all job-board APIs used have free tiers)

---

## Architecture

```
┌──────────────────────┐     ┌──────────────────────┐     ┌──────────────────────┐
│   Next.js frontend   │────▶│   FastAPI backend    │────▶│   12 Job-Board APIs  │
│   (port 3000)        │◀────│   (port 8000)        │◀────│   + Ollama (11434)   │
└──────────────────────┘     └──────────────────────┘     └──────────────────────┘
         │                            │
         │                            │
         ▼                            ▼
   Browser Dashboard           Edge / Chrome
   ATS Scanner                Extension (autofill)
   Refine drawer
   Did-you-apply modal
```

Three subsystems:
- **`job-app-automation/`** — FastAPI backend (this folder). Aggregates jobs, runs ATS scoring, serves the autofill profile to the extension, calls Ollama for LLM rewrites.
- **`frontend/`** — Next.js 15 dashboard for resume upload, job search, ATS scanner, Kanban, history.
- **`extension/`** — Microsoft Edge / Chrome MV3 extension that fills application forms on visited job sites.

---

## Quick Start (Windows)

The simplest way is to run **`START.bat`** from the project root — it boots the backend, waits for AI models to warm up, and starts the frontend.

For manual setup:

```powershell
# 1. Set up Python venv (one-time)
cd job-app-automation
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Install frontend deps (one-time)
cd ..\frontend
npm install

# 3. Start backend (Terminal 1)
cd ..\job-app-automation
venv\Scripts\Activate.ps1
uvicorn main:app --reload --port 8000

# 4. Start frontend (Terminal 2)
cd frontend
npm run dev
```

Open **http://localhost:3000** in your browser.

### Optional: Local LLM (Ollama)

For AI-powered bullet rewrites, summary tailoring, and smart application-question answers:

```powershell
# 1. Install Ollama from https://ollama.com/download
# 2. Pull the default model
ollama pull llama3.2:3b
```

Ollama runs as a background service on port 11434 (auto-starts on Windows). The app gracefully falls back to deterministic templates if Ollama isn't running.

### Optional: Browser Extension

1. Open `edge://extensions` (or `chrome://extensions`)
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked**
4. Select the `extension/` folder

The extension panel appears on apply pages of supported ATS platforms.

---

## Job Boards

### No Credentials Needed (work immediately)

| Board | Focus |
|---|---|
| The Muse | Tech / creative |
| RemoteOK | Remote tech |
| Remotive | Remote all roles |
| Arbeitnow | Tech + remote (global) |
| Jobicy | Remote US startups |
| Himalayas | Remote startup / scale-up |

### Free API Keys (recommended for full coverage)

| Board | Get Key |
|---|---|
| JSearch (Google for Jobs) | [rapidapi.com](https://rapidapi.com) — search "JSearch" |
| Adzuna | [developer.adzuna.com](https://developer.adzuna.com) |
| USAJobs | [developer.usajobs.gov/apirequest](https://developer.usajobs.gov/apirequest) |
| Findwork | [findwork.dev](https://findwork.dev) |
| Jooble | [jooble.org/api/about](https://jooble.org/api/about) |
| Careerjet | [careerjet.com/partners/register/as-publisher](https://www.careerjet.com/partners/register/as-publisher) |

Add keys to `.env` (copy `.env.example`).

---

## How to Use

1. **Resume page** — upload your PDF or DOCX. Skills are auto-extracted; PDF hyperlinks (LinkedIn / GitHub / portfolio) are read from link annotations.
2. **Job Search page** — enter keywords + location, pick boards, run search. Results are AI-scored against your resume and saved to the Kanban pipeline.
3. **Dashboard** — your full pipeline:
   - **Saved**: jobs you haven't applied to yet
   - **Refine for this job** opens a per-job drawer with ATS score, keyword pills, LLM summary rewrite, bullet rewrites with Copy buttons, and an in-place text editor
   - **Apply** opens the job site in a new tab; the extension auto-fills the form. When you return, a modal asks "Did you apply?" — Yes moves the job to Applied, No keeps it in Saved.
4. **ATS Scanner** — standalone scan against any saved job or any pasted JD.
5. **History** — full log, filterable by source / status / H1B / remote.
6. **Settings** — profile preferences (work authorization, sponsorship, expected salary, notice period).

---

## Project Structure (backend)

```
job-app-automation/
├── main.py                   # FastAPI entry point + all HTTP routes
├── config.py                 # Configuration (env vars, paths, AI model name)
├── requirements.txt
├── .env.example              # Copy to .env and fill in your API keys
├── database/
│   ├── db.py                 # All SQLite operations + auto-migration
│   └── models.py             # Resume and Job dataclasses
├── api/
│   ├── aggregator.py         # Single entry point: parallel fetch from all boards
│   ├── jsearch.py            # JSearch (Google for Jobs via RapidAPI)
│   ├── adzuna.py             # Adzuna API
│   ├── themuse.py            # The Muse API
│   ├── usajobs.py            # USAJobs (federal)
│   ├── remoteok.py           # RemoteOK (no auth)
│   ├── remotive.py           # Remotive (no auth)
│   ├── arbeitnow.py          # Arbeitnow (no auth)
│   ├── jobicy.py             # Jobicy (no auth)
│   ├── himalayas.py          # Himalayas (no auth)
│   ├── findwork.py           # Findwork API
│   ├── jooble.py             # Jooble API
│   └── careerjet.py          # Careerjet API
├── matching/
│   ├── embedder.py           # sentence-transformers singleton (cached)
│   ├── scorer.py             # Cosine similarity scoring
│   └── experience.py         # Years-of-experience extraction
├── ats/
│   ├── scanner.py            # KeyBERT extraction + semantic scoring
│   ├── suggestions.py        # Section-aware suggestions + LLM rewrites
│   └── llm_client.py         # Ollama HTTP client + on-disk caching
├── resume/
│   └── profile_extractor.py  # Parses raw text into structured autofill profile
├── utils/
│   ├── parser.py             # Resume PDF/DOCX parser (with hyperlink extraction)
│   ├── locations.py          # City autocomplete list
│   └── job_helpers.py        # Shared scraper utilities
├── uploads/                  # User's uploaded resume bytes (served back to extension)
└── data/
    ├── jobs.db               # SQLite (auto-created, auto-migrated)
    └── rewrite_cache.json    # On-disk cache for LLM rewrites
```

---

## Privacy & Security

- **All data stays on your machine.** Resume text and personal info are never sent to any cloud service.
- **API keys** are stored in your local `.env` file and only sent to the respective job-board API.
- **Resume text and PDF** are stored in local SQLite + `uploads/` only.
- **Ollama runs locally** — your resume content never leaves your laptop when LLM rewrites are generated.
- When contributing / publishing: `.env` is in `.gitignore` — it will NOT be committed.

---

## Running on macOS / Linux

```bash
# Backend
cd job-app-automation
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Or use the `./start.sh` and `./stop.sh` scripts in the project root.

---

*Built with ResumeWing — run it locally, own your data, pay nothing.*
