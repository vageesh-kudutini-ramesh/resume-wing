# ResumeWing

> An open-source, **local-first** job application toolkit.
> Aggregates jobs from 12 free-tier boards, scores your resume against any JD with a real ATS engine, generates LLM-tailored bullet rewrites and summaries, and auto-fills application forms via a browser extension. All data stays on your machine.

---

## Why ResumeWing

The job-application stack today is broken in three ways:

1. **Job aggregators show stale or duplicate listings** and bury you in irrelevant roles.
2. **ATS scanners are a paid SaaS** with vague suggestions like "increase your match by 20%".
3. **Form fillers are unreliable**, mostly target LinkedIn / Indeed (which charge for API access), and you re-type the same answers on every site.

ResumeWing addresses all three by running **entirely on your laptop**:

- **Job search** uses 12 free-tier APIs (no scraping, no LinkedIn / Indeed paywall) and de-duplicates across them.
- **ATS scanner** uses KeyBERT + sentence-transformers for honest scoring, with a **local Ollama LLM** generating natural bullet rewrites and tailored summaries — no cloud LLM cost, no resume content ever leaves your laptop.
- **Browser extension** auto-fills Greenhouse, Lever, Workday, Ashby, SmartRecruiters and falls back to a smart universal classifier on any career-page URL. Handles text, selects, radios, and resume PDF upload via DataTransfer.

---

## Architecture

```
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│  Next.js dashboard  │───▶│  FastAPI backend    │───▶│  12 job-board APIs  │
│  (port 3000)        │◀───│  (port 8000)        │◀───│  + Ollama (11434)   │
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘
         │                          ▲
         │                          │ chrome-extension://
         ▼                          │
   Resume upload              ┌─────┴────────────┐
   Job search                 │  Browser ext.    │
   ATS scanner                │  (Edge / Chrome) │
   Refine drawer              └──────────────────┘
   Did-you-apply modal
```

Three subsystems, each in its own folder:

| Folder | Stack | Role |
|---|---|---|
| `job-app-automation/` | FastAPI + SQLite + KeyBERT + Ollama | Aggregates jobs, scores ATS, hosts the autofill profile API |
| `frontend/` | Next.js 15 + React 19 + Base UI + Tailwind + React Query | Dashboard, ATS Scanner, Refine drawer, Did-you-apply modal |
| `extension/` | Manifest V3 (Edge/Chrome) | Auto-fills application forms; resume PDF upload via DataTransfer |

---

## Quick Start

### Windows (recommended path)

```powershell
# One-time
cd job-app-automation
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt

cd ..\frontend
npm install

# Each time you want to run the app
cd ..
.\START.bat
```

`START.bat` opens two terminal windows (backend + frontend), waits for AI models to warm up, and prints the URLs. Use `STOP.bat` to shut everything down.

### macOS / Linux

```bash
chmod +x start.sh stop.sh
./start.sh
```

### Browser extension (one-time)

1. Open `edge://extensions` (or `chrome://extensions`)
2. Toggle **Developer mode** on (top-right)
3. Click **Load unpacked** → select the `extension/` folder

The floating ResumeWing icon appears on apply pages of supported ATSes.

### Optional — Local LLM (Ollama)

For LLM-powered bullet rewrites, summary tailoring, and smart form-question answers:

```powershell
# Install Ollama from https://ollama.com/download
ollama pull llama3.2:3b
```

Ollama runs as a background service on port 11434. Without it, the app gracefully falls back to deterministic templates — everything still works, just less natural-sounding.

---

## Features

| Feature | What it does |
|---|---|
| **12 job boards** | JSearch, Adzuna, The Muse, RemoteOK, Remotive, Arbeitnow, Jobicy, Himalayas, USAJobs, Findwork, Jooble, Careerjet — searched in parallel and deduped |
| **AI matching** | Local sentence-transformers — every job gets a 0-100% relevance score against your resume |
| **ATS scanner** | KeyBERT keyword extraction + semantic similarity. Returns Found / Implied / Missing keyword lists |
| **LLM bullet rewrites** | Per-job rewrites that incorporate missing keywords *only when grounded in your real experience* — no fabrication |
| **AI summary tailoring** | Local Ollama drafts a tailored Professional Summary per job, with a Copy button |
| **Domain-mismatch warning** | Flags roles where your background genuinely doesn't fit, instead of pushing fabrication |
| **Refine drawer** | One panel per job: ATS score, suggestions, rewrites, in-place editor, Apply button |
| **Did-you-apply modal** | Confirms each application after you click Apply (never auto-marks) |
| **Kanban pipeline** | Saved → Applied → Following Up → Interview → Offer |
| **Browser extension** | Autofills Greenhouse / Lever / Workday / Ashby / SmartRecruiters + universal fallback. Handles text, selects, radios, PDF upload |
| **Smart autofill** | Application questions ("Why are you interested?", work auth, sponsorship) drafted by Ollama, marked yellow for verification |
| **Sensitive field guard** | Never auto-fills gender / race / veteran / disability — those stay for the user to choose |
| **History & filtering** | Full log of every search and application, filterable by source, status, H1B, remote |

**Total recurring cost: $0.** All job-board APIs are free-tier; Ollama runs locally.

---

## Privacy

- All resume content, job history, and form data live in **local SQLite + local files**.
- API keys go into a local `.env` and are sent only to the respective job-board API.
- Ollama runs on your machine — your resume content **never** leaves your laptop when LLM rewrites are generated.
- Nothing is uploaded to any "ResumeWing server"; there is no such server.

---

## Repository layout

```
resume-wing/
├── README.md                ← you are here
├── START.bat / start.sh     ← Windows / macOS / Linux launchers
├── STOP.bat / stop.sh       ← shutdown helpers
├── extension/               ← Edge / Chrome MV3 autofill extension
│   ├── manifest.json
│   ├── background.js
│   ├── content.js
│   └── ats/                 ← per-platform fill modules + smart-autofill
├── frontend/                ← Next.js 15 dashboard
│   ├── app/                 ← app-router pages (resume / search / dashboard / ats / history / settings)
│   ├── components/          ← UI + per-feature components
│   └── lib/                 ← API client, types, utils
└── job-app-automation/      ← FastAPI backend
    ├── main.py              ← all HTTP routes
    ├── api/                 ← 12 job-board clients + aggregator
    ├── ats/                 ← KeyBERT scanner + LLM rewrite engine + Ollama client
    ├── matching/            ← sentence-transformers + cosine scoring
    ├── resume/              ← raw text → structured autofill profile
    ├── database/            ← SQLite + auto-migration
    └── utils/               ← PDF/DOCX parser, locations, helpers
```

A more detailed reference (per-file responsibilities, design choices, board-by-board rate limits) lives in [`job-app-automation/README.md`](job-app-automation/README.md).

---

## Contributing

Contributions are welcome — particularly:

- **More platform-specific autofill modules** (extension/ats/*.js) — Workday in particular has many sub-variants.
- **More job boards** — drop a new client into `job-app-automation/api/` and register it in `aggregator.py`.
- **ATS suggestion templates** for under-served fields (certifications, projects, summary tweaks).

To get started: fork the repo, follow the Quick Start above, make your change, and open a PR. There's no formal contribution process yet — keep changes small and well-described.

---

## License

MIT — do whatever you want with it. See `LICENSE`.

---

*Built to be run locally. Own your data. Pay nothing.*
