# ResumeWing

> An open-source, **local-first** job application toolkit.
> Aggregates jobs from 12 free-tier boards, scores your resume against any JD with a real ATS engine, generates LLM-tailored bullet rewrites and summaries, and auto-fills application forms via a browser extension. All data stays on your machine.

---

## Demo

https://github.com/user-attachments/assets/085fcf01-706f-4ad3-a988-96c7b5bc3065


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

### Optional — Daily digest email

ResumeWing can email you the top N ranked matches for your keywords every morning. The script reuses the same search + scoring engine the dashboard uses, filters out roles you've already applied to or were emailed previously, and ships a clean HTML digest with "View & Apply" and "Open in dashboard" buttons.

**One-time setup (~5 minutes):**

1. Enable 2-Factor Auth on the Gmail account you want to send *from*.
2. Generate an App Password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) — App = `Mail`, Device = `Other (ResumeWing)`. Copy the 16-character string.
3. Add these to your `.env`:

   ```env
   DIGEST_EMAIL_TO=you@example.com
   DIGEST_SMTP_USER=sender@gmail.com
   DIGEST_SMTP_PASSWORD=xxxx xxxx xxxx xxxx
   DIGEST_KEYWORDS=Software Engineer,Backend Engineer,Full Stack Engineer
   DIGEST_LOCATION=United States,Remote
   ```

   `DIGEST_LOCATION` accepts a single value or a comma-separated list. Each value runs its own search cycle; results are deduped across cycles by URL. Heavy quota note: JSearch's free tier is 200/month, so keep `keywords × locations ≤ ~6` to stay under, or run the task 5 days/week.

4. Test it manually:

   ```powershell
   # Windows
   cd job-app-automation
   venv\Scripts\python digest_email.py
   ```

   ```bash
   # macOS / Linux
   cd job-app-automation
   chmod +x run_digest.sh
   venv/bin/python digest_email.py
   ```

5. Once you've received a successful test email, register the daily task. The instructions below configure the scheduler to **wake the laptop from sleep** at 8 AM and **catch up if the machine was off / missed the run** when it next powers on.

#### Windows — Task Scheduler

Register the task, then enable wake-from-sleep + run-if-missed (two short PowerShell commands):

Replace `<REPO_PATH>` below with the absolute path to your cloned copy (e.g. `C:\Users\You\code\resume-wing`):

```powershell
# Step 1 — register the daily 8 AM task
schtasks /Create /TN ResumeWingDigest `
  /TR "<REPO_PATH>\job-app-automation\run_digest.bat" `
  /SC DAILY /ST 08:00 /F

# Step 2 — wake from sleep + run if the scheduled time was missed
$task = Get-ScheduledTask -TaskName ResumeWingDigest
$task.Settings.WakeToRun = $true
$task.Settings.StartWhenAvailable = $true
$task.Settings.RestartCount = 3
$task.Settings.RestartInterval = "PT10M"
Set-ScheduledTask -InputObject $task
```

The same options can be toggled in the Task Scheduler GUI (`taskschd.msc`) — *Conditions → Wake the computer to run this task*, *Settings → Run task as soon as possible after a scheduled start is missed*.

To check the next run time: `schtasks /Query /TN ResumeWingDigest`. To remove: `schtasks /Delete /TN ResumeWingDigest /F`.

#### macOS — launchd (wakes from sleep)

`launchd` is the Apple-native scheduler and is the only one that reliably wakes the Mac from sleep.

1. Make the runner executable:

   ```bash
   chmod +x /full/path/to/resume-wing/job-app-automation/run_digest.sh
   ```

2. Create `~/Library/LaunchAgents/com.resumewing.digest.plist` with:

   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0">
   <dict>
     <key>Label</key><string>com.resumewing.digest</string>
     <key>ProgramArguments</key>
     <array>
       <string>/full/path/to/resume-wing/job-app-automation/run_digest.sh</string>
     </array>
     <key>StartCalendarInterval</key>
     <dict>
       <key>Hour</key><integer>8</integer>
       <key>Minute</key><integer>0</integer>
     </dict>
     <key>RunAtLoad</key><false/>
     <key>StandardOutPath</key><string>/tmp/resumewing-digest.out.log</string>
     <key>StandardErrorPath</key><string>/tmp/resumewing-digest.err.log</string>
   </dict>
   </plist>
   ```

3. Load it (and also schedule a hardware wake event so the Mac comes out of sleep at 7:59 AM):

   ```bash
   launchctl load ~/Library/LaunchAgents/com.resumewing.digest.plist
   sudo pmset repeat wakeorpoweron MTWRFSU 07:59:00
   ```

   `pmset repeat wakeorpoweron` powers the Mac on or wakes it from sleep daily, one minute before the launchd trigger. Verify with `pmset -g sched`.

To remove: `launchctl unload ~/Library/LaunchAgents/com.resumewing.digest.plist && sudo pmset repeat cancel`.

#### Linux — systemd timer (catches missed runs)

systemd timers with `Persistent=true` automatically run a missed job as soon as the system comes online.

1. Make the runner executable:

   ```bash
   chmod +x /full/path/to/resume-wing/job-app-automation/run_digest.sh
   ```

2. Create `~/.config/systemd/user/resumewing-digest.service`:

   ```ini
   [Unit]
   Description=ResumeWing daily digest email
   After=network-online.target
   Wants=network-online.target

   [Service]
   Type=oneshot
   ExecStart=/full/path/to/resume-wing/job-app-automation/run_digest.sh
   ```

3. Create `~/.config/systemd/user/resumewing-digest.timer`:

   ```ini
   [Unit]
   Description=Run ResumeWing digest daily at 08:00

   [Timer]
   OnCalendar=*-*-* 08:00:00
   Persistent=true
   RandomizedDelaySec=2m

   [Install]
   WantedBy=timers.target
   ```

4. Enable and start the timer:

   ```bash
   systemctl --user daemon-reload
   systemctl --user enable --now resumewing-digest.timer
   loginctl enable-linger "$USER"   # so the timer fires even when you're not logged in
   ```

   `loginctl enable-linger` keeps user services running across logouts. For laptops, the timer naturally wakes the system if `rtcwake` is also scheduled — most distros' suspend-then-hibernate behavior handles this without extra config.

To remove: `systemctl --user disable --now resumewing-digest.timer && rm ~/.config/systemd/user/resumewing-digest.{timer,service}`.

#### What happens when the laptop is fully off

Each scheduler above (Task Scheduler `StartWhenAvailable`, launchd + `pmset repeat`, systemd `Persistent=true`) runs the digest **as soon as the laptop next powers on**, instead of skipping the day. You may get the email at 8 AM if it wakes from sleep, or at whatever time you open the laptop if it was completely off.

Leave `DIGEST_EMAIL_TO` blank to disable. Logs land in `job-app-automation/data/digest.log`.

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
