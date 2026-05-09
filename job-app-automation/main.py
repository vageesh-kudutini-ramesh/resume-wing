"""
ResumeWing FastAPI Backend
Run with: uvicorn main:app --reload --port 8000
"""
import json
import os
import re
import tempfile
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from config import UPLOADS_DIR

from database.db import (
    init_db, get_all_jobs, get_stats, save_jobs, save_job,
    get_job_by_id, update_job_status, update_job_ats_score,
    restore_job_to_shortlisted, get_pipeline_jobs, get_jobs_by_status,
    search_jobs_db, get_latest_resume, save_resume, get_all_profile, set_profile,
    clear_shortlisted_jobs, delete_job, clear_all_data,
    record_apply_intent, get_pending_apply_intents, acknowledge_apply_intent,
    get_tailored_resume_text, set_tailored_resume_text, clear_tailored_resume_text,
)
from database.models import Job, Resume


def _preload_models() -> None:
    """
    Load the sentence-transformer model and KeyBERT into memory.
    Called once on startup so the first user request is fast.
    Errors are swallowed — the app still works without AI features.
    """
    try:
        from matching.embedder import get_model
        get_model()
    except Exception:
        pass
    try:
        from ats.scanner import _get_keybert
        _get_keybert()
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-warm AI models in a background thread on server start."""
    init_db()
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _preload_models)
    yield


app = FastAPI(title="ResumeWing API", version="2.0.0", lifespan=lifespan)

# CORS allow-list:
#   - localhost / 127.0.0.1 on port 3000  → the Next.js dashboard
#   - chrome-extension://...               → the autofill extension's service
#                                            worker. host_permissions in MV3
#                                            usually let extension fetches
#                                            bypass CORS, but allowing the
#                                            origin here is defence-in-depth
#                                            for sites where the content
#                                            script (not the worker) makes a
#                                            direct fetch.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=r"^chrome-extension://[A-Za-z0-9_\-]+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic models ────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    keywords: str
    location: str = ""
    boards: List[str] = []
    num_per_board: int = 20
    date_filter: Optional[int] = None
    job_type: Optional[str] = None
    h1b_only: bool = False
    hide_old: bool = True
    replace_existing: bool = True


class ATSScanRequest(BaseModel):
    resume_text: str
    job_description: str
    job_id: Optional[int] = None


class UpdateStatusRequest(BaseModel):
    status: str


class ProfileUpdate(BaseModel):
    candidate_name:        Optional[str]  = None
    candidate_email:       Optional[str]  = None
    default_threshold:     Optional[int]  = None
    # Autofill preferences
    work_authorized:       Optional[bool] = None
    requires_sponsorship:  Optional[bool] = None
    expected_salary:       Optional[str]  = None
    willing_to_relocate:   Optional[bool] = None
    notice_period_days:    Optional[int]  = None


_HTML_TAG_RE     = re.compile(r"<[^>]+>")
_HTML_BLOCK_RE   = re.compile(r"</?(p|div|br|li|ul|ol|h[1-6]|tr|td|table)\b[^>]*>", re.I)
_HTML_SCRIPT_RE  = re.compile(r"<script[^>]*>.*?</script>", re.I | re.S)
_HTML_STYLE_RE   = re.compile(r"<style[^>]*>.*?</style>",  re.I | re.S)


def _strip_html_for_display(text: str) -> str:
    """
    Strip HTML tags and decode common HTML entities for safe plain-text display
    on the dashboard. Mirrors `ats.scanner._strip_html` but lives here so the
    serializer doesn't need to import the scanner module on every request.
    """
    if not text:
        return ""
    text = _HTML_SCRIPT_RE.sub(" ", text)
    text = _HTML_STYLE_RE.sub(" ", text)
    # Block-level tags become newlines so paragraph breaks survive
    text = _HTML_BLOCK_RE.sub("\n", text)
    text = _HTML_TAG_RE.sub(" ", text)
    try:
        import html as _html
        text = _html.unescape(text)
    except Exception:
        pass
    text = text.replace("\xa0", " ").replace("​", "")
    # Collapse runs of whitespace, but keep line breaks
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _job_to_dict(job: Job) -> dict:
    # Job-board APIs (Jooble, Arbeitnow, JSearch) commonly return descriptions
    # with raw HTML — <p>, <b>, &nbsp;, &#x27;, etc. We clean here at
    # serialization time so both existing rows AND future scrapes are
    # rendered as plain text in the dashboard, without needing a DB migration.
    cleaned_full = _strip_html_for_display(job.description) if job.description else ""
    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "description": cleaned_full[:500],
        "description_full": cleaned_full,
        "link": job.link,
        "source": job.source,
        "match_score": job.match_score,
        "ats_score": job.ats_score,
        "status": job.status,
        "pipeline_stage": job.pipeline_stage,
        "location": job.location,
        "date_posted": job.date_posted,
        "remote": job.remote,
        "h1b_mention": job.h1b_mention,
        "salary_text": job.salary_text,
        "contact_email": job.contact_email,
        "scraped_at": job.scraped_at,
        "applied_at": job.applied_at,
        "search_query": job.search_query,
        "apply_intent_at":              job.apply_intent_at,
        "apply_intent_acknowledged_at": job.apply_intent_acknowledged_at,
    }


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


# ── Board status ───────────────────────────────────────────────────────────────

@app.get("/boards/status")
def get_board_status():
    from api.aggregator import get_board_status
    from config import BOARD_DISPLAY
    status = get_board_status()
    result = []
    for name, info in status.items():
        meta = BOARD_DISPLAY.get(name, {})
        result.append({
            "name": name,
            "label": meta.get("label", name),
            "color": meta.get("color", "#666"),
            "tag": meta.get("tag", ""),
            "tier": meta.get("tier", 2),
            "configured": info["configured"],
            "hint": info["hint"],
            "remote_only": info["remote_only"],
        })
    return result


# ── Job Search ─────────────────────────────────────────────────────────────────

@app.post("/jobs/search")
async def search_jobs(req: SearchRequest):
    from api.aggregator import search_all_sources
    from matching.scorer import score_jobs_batch
    from utils.job_helpers import days_since_posted
    from config import EXPIRY_HIDE_DAYS

    try:
        raw_jobs = search_all_sources(
            keywords=req.keywords,
            location=req.location,
            boards=req.boards if req.boards else [],
            num_per_board=req.num_per_board,
            date_filter=req.date_filter,
            job_type=req.job_type,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if req.hide_old:
        raw_jobs = [j for j in raw_jobs if (days_since_posted(j.date_posted) or 0) <= EXPIRY_HIDE_DAYS]
    if req.h1b_only:
        raw_jobs = [j for j in raw_jobs if j.h1b_mention]

    return {"total": len(raw_jobs), "jobs": [_job_to_dict(j) for j in raw_jobs]}


@app.post("/jobs/search-and-save")
async def search_and_save(req: SearchRequest, background_tasks: BackgroundTasks):
    """
    Full search pipeline:
      1. Fetch from all selected boards in parallel
      2. AI-score every result against the current resume (for ranking only)
      3. Extract user's years of experience from resume
      4. Classify each job's seniority level (entry / mid / senior / any)
      5. Save ALL jobs as "shortlisted" — no pre-filtering by score
      6. Return jobs sorted: experience-matched first, then by AI score desc

    The ATS scanner is intentionally NOT used here. It is used per-job
    when the user decides to actually apply (from the Dashboard).
    """
    from api.aggregator import search_all_sources
    from matching.scorer import score_jobs_batch
    from matching.experience import (
        extract_years_of_experience, classify_job_level, is_experience_match,
    )
    from utils.job_helpers import days_since_posted
    from config import EXPIRY_HIDE_DAYS

    resume = get_latest_resume()
    if not resume:
        raise HTTPException(status_code=400, detail="Upload a resume first")

    try:
        raw_jobs = search_all_sources(
            keywords=req.keywords,
            location=req.location,
            boards=req.boards if req.boards else [],
            num_per_board=req.num_per_board,
            date_filter=req.date_filter,
            job_type=req.job_type,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if req.hide_old:
        raw_jobs = [j for j in raw_jobs if (days_since_posted(j.date_posted) or 0) <= EXPIRY_HIDE_DAYS]
    if req.h1b_only:
        raw_jobs = [j for j in raw_jobs if j.h1b_mention]

    if not raw_jobs:
        return {"total_saved": 0, "experience_years": 0, "jobs": []}

    if req.replace_existing:
        clear_shortlisted_jobs()

    # AI scoring (semantic similarity — used for sort order only, NOT for filtering)
    scored = score_jobs_batch(resume_text=resume.text, jobs=raw_jobs)

    # User's years of experience — drives experience-level sort boost
    user_years, exp_method = extract_years_of_experience(resume.text)

    saved_jobs = []
    for job, score in scored:
        job.match_score    = score
        job.search_query   = req.keywords
        job.status         = "shortlisted"
        job.pipeline_stage = "saved"

        # save_job returns the new (or existing duplicate) row ID.
        # We assign it back so _job_to_dict produces a valid, unique id
        # for every job — avoiding the React "duplicate key null" error.
        row_id = save_job(job)
        if row_id is not None:
            job.id = row_id

        job_dict = _job_to_dict(job)
        # Computed fields for the frontend (not persisted to DB)
        job_dict["exp_level"]   = classify_job_level(job.title, job.description)
        job_dict["exp_matched"] = is_experience_match(user_years, job.title, job.description)
        saved_jobs.append(job_dict)

    # Sort: experience-matched jobs first, then by AI match score descending
    saved_jobs.sort(key=lambda j: (0 if j["exp_matched"] else 1, -j["match_score"]))

    return {
        "total_saved":      len(saved_jobs),
        "experience_years": user_years,
        "experience_method": exp_method,
        "jobs":             saved_jobs,
    }


# ── Job CRUD ───────────────────────────────────────────────────────────────────

@app.get("/jobs")
def list_jobs(status: Optional[str] = None, stage: Optional[str] = None, q: Optional[str] = None):
    if q:
        jobs = search_jobs_db(q)
    elif status:
        jobs = get_jobs_by_status(status)
    elif stage:
        jobs = get_pipeline_jobs(stage)
    else:
        jobs = get_all_jobs()
    return [_job_to_dict(j) for j in jobs]


@app.get("/jobs/stats")
def job_stats():
    return get_stats()


@app.get("/jobs/{job_id}")
def get_job(job_id: int):
    job = get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_dict(job)


@app.patch("/jobs/{job_id}/status")
def update_status(job_id: int, req: UpdateStatusRequest):
    update_job_status(job_id, req.status)
    return {"ok": True}


@app.delete("/jobs/{job_id}")
def remove_job(job_id: int):
    """Permanently delete a single job from the database."""
    delete_job(job_id)
    return {"ok": True}


@app.post("/jobs/{job_id}/restore")
def restore_job(job_id: int):
    restore_job_to_shortlisted(job_id)
    return {"ok": True}


# ── Apply-intent flow (Did-you-apply modal) ───────────────────────────────────

class AcknowledgeIntentRequest(BaseModel):
    applied: bool   # True if user actually submitted the application


@app.post("/jobs/{job_id}/apply-intent")
def record_intent(job_id: int):
    """
    Frontend calls this BEFORE opening the external job URL in a new tab.
    Marks that the user is about to apply, so the dashboard can ask
    'Did you apply for this job?' on their return.
    """
    job = get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    record_apply_intent(job_id)
    return {"ok": True, "intent_at": datetime.now().isoformat()}


@app.get("/jobs/apply-intents/pending")
def list_pending_intents():
    """
    Return all jobs the user clicked Apply on but hasn't yet acknowledged.
    The dashboard polls this on focus and shows the modal for the most
    recent unacknowledged job.
    """
    jobs = get_pending_apply_intents()
    return [_job_to_dict(j) for j in jobs]


# ── Tailored resume per job (Phase 3c) ────────────────────────────────────────

class TailoredResumeRequest(BaseModel):
    text: str


@app.get("/jobs/{job_id}/tailored-resume")
def get_tailored(job_id: int):
    """
    Return the user's per-job tailored resume text, or fall back to the
    master resume text so the dashboard always has something to show in
    the editor.
    """
    job = get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    tailored = get_tailored_resume_text(job_id)
    if tailored is not None:
        return {"text": tailored, "is_tailored": True, "source": "tailored"}

    master = get_latest_resume()
    return {
        "text":        master.text if master else "",
        "is_tailored": False,
        "source":      "master" if master else "none",
    }


@app.post("/jobs/{job_id}/tailored-resume")
def save_tailored(job_id: int, req: TailoredResumeRequest):
    """Save the user's edited resume text for this specific job."""
    job = get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    set_tailored_resume_text(job_id, req.text)
    return {"ok": True}


@app.delete("/jobs/{job_id}/tailored-resume")
def reset_tailored(job_id: int):
    """Discard the per-job tailored text and revert to master."""
    clear_tailored_resume_text(job_id)
    return {"ok": True}


@app.post("/jobs/{job_id}/apply-intent/acknowledge")
def acknowledge_intent(job_id: int, req: AcknowledgeIntentRequest):
    """
    User answered 'Did you apply?'.
      applied=True  → status flips to applied_link, job moves to Applied stage.
      applied=False → only the acknowledgement is recorded; the job stays put.
    Either way, this specific click is now settled. A future Apply click
    will re-trigger the modal for the same job.
    """
    job = get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    acknowledge_apply_intent(job_id, req.applied)
    return {"ok": True, "applied": req.applied}


# ── Database management ────────────────────────────────────────────────────────

class ClearDataRequest(BaseModel):
    include_resume: bool = False  # Default: keep the uploaded resume


@app.post("/database/clear")
def clear_database(req: ClearDataRequest):
    """
    Reset all stored data. By default keeps the uploaded resume so the user
    doesn't have to re-upload.  Set include_resume=true to wipe everything.
    """
    counts = clear_all_data(include_resume=req.include_resume)
    return {"ok": True, **counts}


# ── ATS Scanner ────────────────────────────────────────────────────────────────

@app.post("/ats/scan")
def ats_scan(req: ATSScanRequest):
    from ats.scanner import run_ats_scan, parse_resume_sections
    from ats.suggestions import generate_suggestions, generate_bullet_rewrites, generate_summary_rewrite

    result          = run_ats_scan(req.resume_text, req.job_description)
    suggestions     = generate_suggestions(result)
    bullet_rewrites = generate_bullet_rewrites(result.get("bullet_matches", {}))

    # Generate an LLM-tailored summary rewrite when:
    #   - The resume has a summary section we can rewrite (or doesn't, in
    #     which case we propose creating one from scratch), AND
    #   - The score isn't already excellent (≥85% means no tweaking needed)
    summary_rewrite = None
    if result["ats_score"] < 85:
        sections = parse_resume_sections(req.resume_text)
        current_summary = (sections.get("summary") or "").strip()
        # JD context = first 600 chars of the JD (after our HTML/boilerplate strip
        # in run_ats_scan, the relevant signals are at the top)
        jd_context = req.job_description[:600] if req.job_description else ""
        try:
            summary_rewrite = generate_summary_rewrite(
                current_summary=current_summary,
                missing_keywords=result.get("missing_keywords", []),
                resume_text=req.resume_text,
                jd_context=jd_context,
            )
        except Exception:
            summary_rewrite = None

    if req.job_id:
        update_job_ats_score(req.job_id, result["ats_score"])

    return {
        "ats_score":          result["ats_score"],
        "keyword_score":      result["keyword_score"],
        "semantic_score":     result["semantic_score"],
        "found_keywords":     result["found_keywords"],
        "implied_keywords":   result.get("implied_keywords", []),
        "missing_keywords":   result["missing_keywords"],
        "missing_by_section": result["missing_by_section"],
        "resume_sections":    result["resume_sections"],
        "nlp_mode":           result["nlp_mode"],
        "suggestions":        suggestions,
        "bullet_rewrites":    bullet_rewrites,
        "summary_rewrite":    summary_rewrite,
    }


# ── Resume ─────────────────────────────────────────────────────────────────────

@app.post("/resume/upload")
async def upload_resume(file: UploadFile = File(...)):
    from utils.parser import parse_resume, extract_contact_info, extract_name

    allowed = {".pdf", ".docx"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")

    content = await file.read()
    text, skills, hyperlinks = parse_resume(file.filename or "resume.pdf", content)

    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract text from this file")

    contact = extract_contact_info(text)
    name = extract_name(text)

    # Persist the original bytes so the extension can later fetch them and
    # upload the same file to job application forms via the DataTransfer API.
    safe_name = os.path.basename(file.filename or "resume.pdf")
    saved_path = UPLOADS_DIR / safe_name
    try:
        with open(saved_path, "wb") as fh:
            fh.write(content)
    except Exception:
        # If disk save fails the upload still succeeds — we just lose the
        # ability to auto-upload via the extension on this resume.
        saved_path = None

    resume = Resume(filename=safe_name, text=text, skills=json.dumps(skills))
    save_resume(resume)

    return {
        "filename":    safe_name,
        "text_length": len(text),
        "skills":      skills,
        "name":        name,
        "email":       contact.get("email"),
        "phone":       contact.get("phone"),
    }


@app.post("/resume/reparse")
def reparse_resume():
    """
    Re-extract text + skills from the resume bytes already on disk and
    overwrite the latest resume row. Useful when the parser has been improved
    (e.g. now extracting PDF hyperlink annotations) and the user shouldn't
    have to re-upload the same file.
    """
    from utils.parser import parse_resume

    resume = get_latest_resume()
    if not resume or not resume.filename:
        raise HTTPException(status_code=404, detail="No resume on file to reparse.")

    path = UPLOADS_DIR / resume.filename
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="Resume file bytes are missing on disk. Please re-upload your resume.",
        )

    with open(path, "rb") as fh:
        content = fh.read()

    text, skills, _hyperlinks = parse_resume(resume.filename, content)
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract text from this file")

    new_resume = Resume(filename=resume.filename, text=text, skills=json.dumps(skills))
    save_resume(new_resume)

    return {
        "ok":          True,
        "filename":    resume.filename,
        "text_length": len(text),
        "skills":      skills,
    }


@app.get("/resume/file")
def download_resume_file():
    """
    Serve the latest uploaded resume's raw bytes back to the extension so it
    can synthesize a File object and inject it into a job site's
    `<input type="file">` via the DataTransfer API.
    """
    resume = get_latest_resume()
    if not resume or not resume.filename:
        raise HTTPException(status_code=404, detail="No resume uploaded")

    path = UPLOADS_DIR / resume.filename
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="Resume metadata exists but file bytes are missing — re-upload to enable extension auto-upload.",
        )

    media = "application/pdf" if str(path).lower().endswith(".pdf") \
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(path, media_type=media, filename=resume.filename)


@app.get("/resume")
def get_resume():
    resume = get_latest_resume()
    if not resume:
        return None
    skills = json.loads(resume.skills) if resume.skills else []
    return {
        "filename": resume.filename,
        "text": resume.text,
        "skills": skills,
        "uploaded_at": resume.uploaded_at,
    }


@app.get("/resume/experience")
def get_resume_experience():
    """
    Extract the user's years of experience from the latest resume.
    Returns years, the detection method, and a human-readable level label.
    """
    from matching.experience import extract_years_of_experience, classify_user_level

    resume = get_latest_resume()
    if not resume:
        raise HTTPException(status_code=404, detail="No resume uploaded yet")

    years, method = extract_years_of_experience(resume.text)
    level = classify_user_level(years)
    return {
        "years":  years,
        "method": method,
        "level":  level,
    }


# ── Profile ────────────────────────────────────────────────────────────────────

@app.get("/profile")
def get_profile():
    return get_all_profile()


@app.patch("/profile")
def update_profile(req: ProfileUpdate):
    if req.candidate_name       is not None: set_profile("candidate_name",       req.candidate_name)
    if req.candidate_email      is not None: set_profile("candidate_email",       req.candidate_email)
    if req.default_threshold    is not None: set_profile("default_threshold",     str(req.default_threshold))
    if req.work_authorized      is not None: set_profile("work_authorized",       str(req.work_authorized).lower())
    if req.requires_sponsorship is not None: set_profile("requires_sponsorship",  str(req.requires_sponsorship).lower())
    if req.expected_salary      is not None: set_profile("expected_salary",       req.expected_salary)
    if req.willing_to_relocate  is not None: set_profile("willing_to_relocate",   str(req.willing_to_relocate).lower())
    if req.notice_period_days   is not None: set_profile("notice_period_days",    str(req.notice_period_days))
    return {"ok": True}


@app.get("/profile/autofill")
def get_autofill_profile():
    """
    Return the full structured autofill profile used by the browser extension.

    Combines:
      - Parsed resume text (name, contact, work history, education, skills)
      - PDF hyperlink annotations on disk — authoritative source for
        LinkedIn / GitHub / portfolio URLs (text often loses them)
      - Stored user preferences (work authorization, sponsorship, salary)

    The extension caches this locally and refreshes on each page load.
    """
    from resume.profile_extractor import extract_autofill_profile
    from utils.parser import extract_text_from_pdf
    import json

    resume = get_latest_resume()
    if not resume:
        raise HTTPException(
            status_code=404,
            detail="No resume uploaded. Upload a resume first on the Resume page.",
        )

    raw_skills     = json.loads(resume.skills) if resume.skills else []
    stored_profile = get_all_profile()

    # Re-extract PDF hyperlinks from the file on disk so the URL annotations
    # are passed cleanly to the profile extractor (rather than appended to
    # the resume text where they polluted the certifications section).
    pdf_hyperlinks: List[str] = []
    if resume.filename and resume.filename.lower().endswith(".pdf"):
        path = UPLOADS_DIR / resume.filename
        if path.exists():
            try:
                with open(path, "rb") as fh:
                    _text, pdf_hyperlinks = extract_text_from_pdf(fh.read())
            except Exception:
                pdf_hyperlinks = []

    profile = extract_autofill_profile(
        resume_text    = resume.text,
        raw_skills     = raw_skills,
        stored_profile = stored_profile,
        pdf_hyperlinks = pdf_hyperlinks,
    )
    return profile


# ── Universal Autofill — AI field classifier ──────────────────────────────────

class ClassifyFieldRequest(BaseModel):
    label:       str = ""
    placeholder: str = ""
    name:        str = ""
    id:          str = ""
    aria_label:  str = ""
    surrounding: str = ""


# Canonical semantic descriptions for every field type the universal classifier knows.
# Richer descriptions → better semantic matching for ambiguous labels.
_FIELD_DESCRIPTIONS: dict[str, str] = {
    "first_name":        "first name given name legal first name applicant first name forename",
    "last_name":         "last name family name surname applicant last name",
    "full_name":         "full name complete name legal name applicant name",
    "email":             "email address contact email work email",
    "phone":             "phone number mobile number telephone cell number contact number",
    "city":              "city town municipality city of residence current city",
    "state":             "state province region",
    "zip":               "zip code postal code post code pin code",
    "country":           "country country of residence nationality",
    "address":           "street address mailing address address line 1",
    "linkedin":          "linkedin url linkedin profile linkedin link",
    "github":            "github url github profile github repository code portfolio",
    "portfolio":         "portfolio website personal site personal website blog homepage",
    "current_company":   "current company current employer organization company name employer",
    "job_title":         "current title job title current role designation current position",
    "years_experience":  "years of experience total experience how many years experience",
    "expected_salary":   "expected salary desired salary compensation ctc expected ctc salary expectation",
    "notice_period":     "notice period weeks notice days notice serving notice",
    "start_date":        "start date available from when can you start joining date availability",
    "work_authorization":"work authorization authorized to work eligible to work right to work visa sponsorship work permit citizenship",
    "how_did_you_hear":  "how did you hear referred by referral source discover",
    "cover_letter":      "cover letter motivation letter why do you want tell us about additional information message",
    "school":            "school university college institution alma mater",
    "degree":            "degree highest degree level of education qualification",
    "major":             "major field of study concentration area of study specialization",
    "graduation_year":   "graduation year year of graduation graduation date pass out year",
}


@app.post("/profile/classify-field")
def classify_field(req: ClassifyFieldRequest):
    """
    AI-powered form field classifier for the browser extension's universal filler.

    Called for fields that the extension's local pattern library couldn't classify.
    Uses the pre-loaded sentence-transformers model to compute cosine similarity
    between the field's text signals and canonical field-type descriptions.

    Returns the best matching field key + a confidence score in [0, 1].
    If the best score is below 0.35 the response returns field_key=null,
    meaning the field is genuinely ambiguous and the user should label it manually.
    """
    from matching.embedder import get_model

    # Build a single query string from all available signals
    query_parts = [
        req.label, req.placeholder, req.aria_label, req.name, req.id, req.surrounding,
    ]
    query = " ".join(p for p in query_parts if p and p.strip())

    if not query.strip():
        return {"field_key": None, "confidence": 0.0, "confidence_pct": 0}

    model = get_model()

    keys   = list(_FIELD_DESCRIPTIONS.keys())
    texts  = [query] + list(_FIELD_DESCRIPTIONS.values())

    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    query_emb  = embeddings[0]
    desc_embs  = embeddings[1:]

    # Cosine similarity (dot product of unit vectors)
    similarities = [float(query_emb @ desc) for desc in desc_embs]

    best_idx   = int(max(range(len(similarities)), key=lambda i: similarities[i]))
    best_score = similarities[best_idx]
    best_key   = keys[best_idx]

    # Only trust the classification above a meaningful threshold
    MIN_CONFIDENCE = 0.35
    if best_score < MIN_CONFIDENCE:
        return {"field_key": None, "confidence": round(best_score, 3), "confidence_pct": 0}

    return {
        "field_key":      best_key,
        "confidence":     round(best_score, 3),
        "confidence_pct": round(best_score * 100, 1),
    }


# ── Smart autofill: answer application questions using Ollama ─────────────────

class AnswerQuestionRequest(BaseModel):
    question:    str
    field_type:  str = "input"            # "input" (single-line) | "textarea"
    jd_context:  Optional[str] = None     # job title / company / brief JD
    max_length:  Optional[int] = None     # maxlength of the form field, if known


# Categorical question patterns we can answer directly from the stored profile
# without spending an LLM call. Each entry: (regex, builder(profile, prefs) -> answer or None)
_CATEGORICAL_RULES = [
    # Work authorization
    (
        re.compile(r"(authoriz|legal(?:ly)?\s+(?:able|allowed)|right\s+to\s+work|eligib(?:le|ility)\s+to\s+work|us\s+work)\b", re.I),
        lambda profile, prefs: ("Yes" if prefs.get("work_authorized", True) else "No"),
    ),
    # Sponsorship
    (
        re.compile(r"\b(sponsor(?:ship)?|h-?1b|visa)\b", re.I),
        lambda profile, prefs: ("Yes" if prefs.get("requires_sponsorship") else "No"),
    ),
    # Notice period
    (
        re.compile(r"\bnotice\s+period\b", re.I),
        lambda profile, prefs: (
            f"{int(prefs.get('notice_period_days', 0))} days"
            if prefs.get("notice_period_days") else None
        ),
    ),
    # Expected salary / compensation
    (
        re.compile(r"(expected|desired|target)\s+(salary|compensation|ctc|pay)", re.I),
        lambda profile, prefs: prefs.get("expected_salary") or None,
    ),
    # Willingness to relocate
    (
        re.compile(r"\b(willing\s+to\s+relocate|relocation)\b", re.I),
        lambda profile, prefs: ("Yes" if prefs.get("willing_to_relocate") else "No"),
    ),
    # Start date / availability
    (
        re.compile(r"\b(start\s+date|when\s+can\s+you\s+start|availab(?:le|ility))\b", re.I),
        lambda profile, prefs: (
            "Immediately" if not prefs.get("notice_period_days") else
            f"After a {int(prefs.get('notice_period_days', 0))}-day notice period"
        ),
    ),
]


def _categorical_answer(question: str, profile: Dict) -> Optional[Tuple[str, str]]:
    """If the question matches a known categorical pattern, return (answer, source)."""
    prefs = profile.get("preferences") or {}
    for pattern, builder in _CATEGORICAL_RULES:
        if pattern.search(question):
            try:
                ans = builder(profile, prefs)
            except Exception:
                ans = None
            if ans:
                return ans, "profile"
    return None


_ANSWER_PROMPT_INPUT = """You are helping a job applicant fill in an application form field.

The applicant's resume is below. You will be given a question from the form. Write a SHORT, factual answer (one sentence, max 200 characters) that is fully supported by the resume — do NOT invent skills, projects, employers, metrics, or any fact the resume does not state. If the resume does not contain enough information to answer truthfully, output exactly: NEEDS_USER_INPUT

Output ONLY the answer text. No quotes, no preamble, no explanation.

RESUME:
{resume_text}

JOB CONTEXT (optional):
{jd_context}

QUESTION:
{question}

ANSWER:"""

_ANSWER_PROMPT_TEXTAREA = """You are helping a job applicant fill in an application form's open-ended text field.

The applicant's resume is below. Write a 2–4 sentence answer to the question that is fully supported by the resume — do NOT invent skills, projects, employers, metrics, or any fact the resume does not state. Match the resume's tone (professional, concrete, action-oriented). If the resume does not contain enough information to answer truthfully, output exactly: NEEDS_USER_INPUT

Output ONLY the answer text. No quotes, no preamble, no explanation, no bullet points.

RESUME:
{resume_text}

JOB CONTEXT (optional):
{jd_context}

QUESTION:
{question}

ANSWER:"""


@app.post("/profile/answer-question")
def answer_question(req: AnswerQuestionRequest):
    """
    Generate a draft answer for an application form question.

    Strategy:
      1. If the question matches a known categorical pattern (work auth,
         sponsorship, notice period, salary, etc.) answer from the stored
         profile preferences directly — no LLM call.
      2. Otherwise call local Ollama with a strict no-fabrication prompt.
      3. The extension fills the resulting answer as "needs verification"
         (yellow) so the user reviews before submitting the form.
    """
    from ats import llm_client
    from resume.profile_extractor import extract_autofill_profile

    resume = get_latest_resume()
    if not resume:
        raise HTTPException(status_code=404, detail="No resume uploaded")

    raw_skills    = json.loads(resume.skills) if resume.skills else []
    stored        = get_all_profile()
    profile       = extract_autofill_profile(
        resume_text=resume.text, raw_skills=raw_skills, stored_profile=stored,
    )

    # ── 1. Categorical fast path ─────────────────────────────────────────────
    cat = _categorical_answer(req.question, profile)
    if cat:
        answer, source = cat
        return {"answer": answer, "confidence": 0.95, "source": source}

    # ── 2. LLM path (Ollama) ─────────────────────────────────────────────────
    if not llm_client.is_available():
        return {"answer": "", "confidence": 0.0, "source": "unavailable"}

    template = _ANSWER_PROMPT_TEXTAREA if req.field_type == "textarea" else _ANSWER_PROMPT_INPUT
    prompt   = template.format(
        resume_text=resume.text[:4000],   # cap to keep prompt small
        jd_context=(req.jd_context or "").strip() or "(none)",
        question=req.question.strip(),
    )

    raw = llm_client.generate(prompt, temperature=0.4, max_tokens=180)
    if not raw:
        return {"answer": "", "confidence": 0.0, "source": "llm_failed"}

    answer = raw.strip().strip('"').strip("'").splitlines()[0] \
        if req.field_type == "input" else raw.strip().strip('"').strip("'")

    if "NEEDS_USER_INPUT" in answer or not answer:
        return {"answer": "", "confidence": 0.0, "source": "needs_user_input"}

    # Length cap if the form told us
    if req.max_length and len(answer) > req.max_length:
        answer = answer[:req.max_length].rstrip()

    return {"answer": answer, "confidence": 0.7, "source": "ollama"}
