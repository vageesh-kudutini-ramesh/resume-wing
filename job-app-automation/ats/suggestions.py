"""
Resume improvement suggestions generated from ATS scan results.

Engines
───────
1. Bullet rewrite engine (Ollama):
   For each missing keyword that has a semantically matched experience/projects
   bullet, ask the local LLM to produce a natural rewrite that incorporates
   the keyword without inventing facts. Skills lines are excluded.

2. Summary rewrite engine (Ollama):
   When the user's summary doesn't match the JD's domain, ask the LLM to
   produce a tailored 2-3 sentence summary using the JD's language but
   strictly grounded in the resume's actual experience.

3. Section-presence detector:
   Some resumes lack Summary / Projects / Certifications sections entirely.
   Suggestions adapt: instead of "tweak your summary", we say "add a
   Summary section — here's a starter".

Local LLM (Ollama) is the default. Falls back to deterministic templates
when Ollama is unavailable.
"""
import re
from typing import Dict, List, Optional

from ats import llm_client


# ── Skill category detection (purely cosmetic — labels for the UI) ────────────

_CATEGORIES: Dict[str, List[str]] = {
    "Cloud & Infrastructure": ["aws","azure","gcp","cloud","terraform","ansible",
                                "kubernetes","docker","helm","ec2","s3","lambda"],
    "Frontend":               ["react","angular","vue","typescript","javascript",
                                "html","css","tailwind","webpack","nextjs"],
    "Backend / APIs":         ["python","java","node","django","spring","flask",
                                "rest","api","grpc","fastapi","express","rails"],
    "Data & Analytics":       ["sql","pandas","spark","hadoop","etl","bigquery",
                                "snowflake","airflow","dbt","data pipeline","redshift"],
    "AI / Machine Learning":  ["machine learning","deep learning","tensorflow",
                                "pytorch","nlp","llm","scikit","xgboost","mlops",
                                "embeddings","langchain","openai"],
    "DevOps & CI/CD":         ["ci/cd","jenkins","github actions","gitlab","devops",
                                "monitoring","grafana","prometheus","datadog","sre"],
    "Mobile":                 ["ios","android","react native","flutter","swift","kotlin"],
    "Security":               ["cybersecurity","penetration testing","soc","encryption",
                                "ssl","tls","oauth","saml","devsecops","owasp"],
    "Agile / Leadership":     ["agile","scrum","kanban","leadership","mentoring",
                                "stakeholder","cross-functional","product roadmap"],
    "Testing / QA":           ["testing","selenium","cypress","jest","pytest","junit",
                                "qa","quality assurance","tdd","bdd"],
}


def _categorise(keywords: List[str]) -> str:
    kw_text = " ".join(keywords).lower()
    best_cat = "Technical Skills"
    best_score = 0
    for category, vocab in _CATEGORIES.items():
        score = sum(1 for v in vocab if v in kw_text)
        if score > best_score:
            best_score = score
            best_cat = category
    return best_cat


# ── LLM prompt builder ────────────────────────────────────────────────────────

_REWRITE_PROMPT = """You are a resume editor. Your job is to rewrite ONE existing resume bullet so it naturally incorporates a keyword, without inventing any facts that weren't in the original.

STRICT RULES:
1. Output ONLY the rewritten bullet. No preamble, no quotes, no explanation, no bullet markers.
2. Do NOT invent technologies, frameworks, projects, metrics, percentages, or company names that the original bullet does not mention. You may rephrase, you may not fabricate.
3. The rewrite MUST be grammatically correct and read naturally — do NOT just append the keyword at the end.
4. Stay within 80% to 130% of the original bullet's length.
5. Keep the same tense as the original (past tense if the original uses past tense).
6. If the keyword cannot be incorporated truthfully (e.g. the bullet is about something completely unrelated), output the EXACT original bullet unchanged.
7. The keyword may be inserted, replaced, or used to specify an existing concept — choose what reads most naturally.

ORIGINAL BULLET:
{bullet}

KEYWORD TO INCORPORATE:
{keyword}

REWRITTEN BULLET:"""


def _build_prompt(bullet: str, keyword: str) -> str:
    return _REWRITE_PROMPT.format(bullet=bullet.strip(), keyword=keyword.strip())


# ── LLM response cleaning ─────────────────────────────────────────────────────

def _clean_llm_response(raw: Optional[str], bullet: str, keyword: str) -> Optional[str]:
    """
    Clean and validate an LLM response. Returns the rewrite or None if invalid.

    Validations:
      - Non-empty after stripping
      - Contains the keyword (case-insensitive) — if absent, the LLM ignored
        the instruction and we fall back to template
      - Length between 60% and 180% of original (loose bounds — strict bounds
        reject too many fine rewrites)
      - Doesn't contain prompt-leakage markers ("REWRITTEN BULLET:", etc.)
    """
    if not raw:
        return None

    text = raw.strip()
    # Strip common prompt leakage and chat scaffolding
    for marker in ("REWRITTEN BULLET:", "Rewritten bullet:", "Here is", "Here's"):
        if text.startswith(marker):
            text = text[len(marker):].lstrip(":").strip()

    # Strip surrounding quotes
    if (text.startswith('"') and text.endswith('"')) or \
       (text.startswith("'") and text.endswith("'")):
        text = text[1:-1].strip()

    # Strip leading bullet markers if the model added them
    text = text.lstrip("-•*▪►→ ").strip()

    # Take just the first paragraph — multi-paragraph output usually means
    # the model added an explanation
    text = text.split("\n\n")[0].strip()
    # And just the first line if it's a multi-line bullet
    text = text.split("\n")[0].strip()

    if not text:
        return None

    # Length sanity check
    orig_len = max(1, len(bullet))
    if len(text) < orig_len * 0.6 or len(text) > orig_len * 1.8:
        return None

    # Keyword must appear (case-insensitive) — otherwise the LLM ignored us
    if keyword.lower() not in text.lower():
        return None

    return text


# ── Template fallback ─────────────────────────────────────────────────────────
# Used only when Ollama is unavailable OR the LLM returns an invalid response.
# Marked in the result dict with `engine: "template"` so the UI can label it.

_CLOUD_PLATFORMS  = {"aws","azure","gcp","ec2","s3","lambda","fargate","ecs","eks",
                      "cloud","cloudwatch","cloudformation","heroku","vercel","netlify"}
_CONTAINER_TOOLS  = {"docker","kubernetes","k8s","helm","podman","containerd","istio"}
_DB_TOOLS         = {"postgresql","postgres","mysql","mongodb","redis","elasticsearch",
                      "dynamodb","cassandra","snowflake","redshift","bigquery","sqlite",
                      "neo4j","couchdb","influxdb"}
_CICD_TOOLS       = {"ci/cd","cicd","jenkins","github actions","gitlab ci","argocd",
                      "fluxcd","circle ci","travis ci","teamcity","bamboo"}
_IaC_TOOLS        = {"terraform","pulumi","ansible","chef","puppet","cloudformation"}
_MONITORING       = {"prometheus","grafana","datadog","splunk","cloudwatch","sentry",
                      "newrelic","dynatrace","elk","kibana","jaeger"}
_TESTING_TOOLS    = {"pytest","junit","jest","cypress","selenium","playwright","mocha",
                      "chai","testng","postman","jmeter","locust"}
_METHODOLOGIES    = {"agile","scrum","kanban","tdd","bdd","lean","sre","devops","gitops",
                      "sprint","retro","pair programming","code review"}


def _connector_for(keyword: str) -> str:
    kw = keyword.lower()
    if kw in _CONTAINER_TOOLS:  return f"containerized with {keyword}"
    if kw in _CLOUD_PLATFORMS:  return f"deployed on {keyword}"
    if kw in _IaC_TOOLS:        return f"provisioned via {keyword}"
    if kw in _CICD_TOOLS:       return f"automated with {keyword}"
    if kw in _MONITORING:       return f"monitored using {keyword}"
    if kw in _DB_TOOLS:         return f"backed by {keyword}"
    if kw in _TESTING_TOOLS:    return f"validated with {keyword}"
    if kw in _METHODOLOGIES:    return f"following {keyword} practices"
    if " " in keyword:          return f"leveraging {keyword}"
    return f"using {keyword}"


def _template_rewrite(bullet: str, keyword: str) -> str:
    """Deterministic fallback when the LLM is unavailable or invalid."""
    base = bullet.rstrip(".!?").rstrip()
    return f"{base}, {_connector_for(keyword)}."


# ── Highlight helper ──────────────────────────────────────────────────────────

def _highlight_addition(original: str, rewrite: str) -> Dict[str, str]:
    """Compute the added portion for green-highlight rendering in the UI."""
    if rewrite.startswith(original.rstrip(".!?")):
        added = rewrite[len(original.rstrip(".!?")):]
        return {"original": original, "added": added.strip(", ").rstrip(".")}
    return {"original": original, "added": rewrite}


# ── Main batch rewrite function ───────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Summary rewrite engine
# ─────────────────────────────────────────────────────────────────────────────

_SUMMARY_REWRITE_PROMPT = """You are a resume editor. Rewrite the candidate's professional summary so it aligns with a specific job posting, while staying STRICTLY grounded in the candidate's actual experience.

CONTEXT:
=== CANDIDATE'S CURRENT SUMMARY ===
{current_summary}

=== KEY MISSING KEYWORDS FROM THE JOB ===
{missing_keywords}

=== JOB TITLE / COMPANY / RESPONSIBILITIES ===
{jd_context}

=== CANDIDATE'S RELEVANT EXPERIENCE (from resume) ===
{resume_excerpt}

STRICT RULES:
1. Output ONLY the rewritten summary. No preamble, no quotes, no explanation, no labels.
2. Stay 2 to 4 sentences. Total length: 350-700 characters.
3. Do NOT invent technologies, frameworks, projects, employers, metrics, or domains the resume doesn't show. Use ONLY skills/experience present in the resume.
4. Naturally incorporate keywords from the missing list IF AND ONLY IF the resume already shows that experience. Skip any keyword the resume can't truthfully back up.
5. Use the same tense and voice as the original. Keep it professional, concrete, and action-oriented.
6. If the candidate's experience genuinely doesn't match the role, return the EXACT original summary unchanged.

REWRITTEN SUMMARY:"""


def _build_summary_prompt(current_summary: str, missing_keywords: List[str],
                          resume_excerpt: str, jd_context: str) -> str:
    return _SUMMARY_REWRITE_PROMPT.format(
        current_summary=current_summary.strip() or "(No summary section yet)",
        missing_keywords=", ".join(missing_keywords[:10]) if missing_keywords else "(none flagged)",
        jd_context=(jd_context or "").strip()[:600] or "(no JD context)",
        resume_excerpt=(resume_excerpt or "").strip()[:1500],
    )


def _clean_summary_response(raw: Optional[str], current_summary: str) -> Optional[str]:
    """Clean and validate the LLM's summary rewrite."""
    if not raw:
        return None
    text = raw.strip().strip('"').strip("'")
    for marker in ("REWRITTEN SUMMARY:", "Rewritten summary:", "Here is", "Here's", "Summary:"):
        if text.startswith(marker):
            text = text[len(marker):].lstrip(":").strip()
    # Take the first paragraph block
    text = text.split("\n\n")[0].strip()
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)

    if not text or len(text) < 60 or len(text) > 900:
        return None
    # Sentence count sanity
    sentence_count = len(re.findall(r"[.!?]+", text))
    if sentence_count < 1 or sentence_count > 6:
        return None
    # Reject if it's identical to the current summary (no value added)
    if current_summary and text.strip() == current_summary.strip():
        return None
    return text


def generate_summary_rewrite(
    current_summary: str,
    missing_keywords: List[str],
    resume_text: str,
    jd_context: str,
) -> Optional[Dict]:
    """
    Produce an LLM-generated summary tailored to a specific job, or None if
    Ollama is unavailable / produced an unusable response. Returns a dict
    matching the bullet-rewrite shape so the frontend can render it
    consistently.
    """
    if not jd_context:
        return None
    if not llm_client.is_available():
        return None

    # Use the experience portion of the resume as grounding context
    resume_excerpt = resume_text[:2500] if resume_text else ""

    prompt = _build_summary_prompt(
        current_summary=current_summary,
        missing_keywords=missing_keywords,
        resume_excerpt=resume_excerpt,
        jd_context=jd_context,
    )
    raw = llm_client.generate(prompt, temperature=0.4, max_tokens=300)
    cleaned = _clean_summary_response(raw, current_summary)
    if not cleaned:
        return None

    return {
        "type":     "summary_rewrite",
        "section":  "summary",
        "original": current_summary or "",
        "rewrite":  cleaned,
        "engine":   "llm",
        "is_new":   not bool(current_summary.strip()) if current_summary else True,
    }


def generate_bullet_rewrites(bullet_matches: Dict[str, Dict]) -> List[Dict]:
    """
    Convert bullet_matches into a list of {keyword, original, rewrite, ...} dicts.

    Internally: collects all (bullet, keyword) pairs and runs them through
    `llm_client.generate_batch` which handles concurrency, caching, and the
    Ollama-availability check. Pairs that come back None (LLM offline or
    invalid output) get the template fallback.
    """
    if not bullet_matches:
        return []

    pairs: List[tuple] = []
    pair_to_kw: Dict[tuple, str] = {}
    pair_to_match: Dict[tuple, Dict] = {}

    for keyword, match in bullet_matches.items():
        bullet = match["bullet_text"]
        pair = (bullet, keyword)
        pairs.append(pair)
        pair_to_kw[pair] = keyword
        pair_to_match[pair] = match

    llm_results = llm_client.generate_batch(
        items=pairs,
        prompt_builder=_build_prompt,
        response_cleaner=_clean_llm_response,
    )

    rewrites: List[Dict] = []
    for pair in pairs:
        bullet, keyword = pair
        match = pair_to_match[pair]
        llm_text = llm_results.get(pair)

        if llm_text:
            rewrite = llm_text
            engine  = "llm"
        else:
            rewrite = _template_rewrite(bullet, keyword)
            engine  = "template"

        added = _highlight_addition(bullet, rewrite)

        rewrites.append({
            "keyword":    keyword,
            "original":   bullet,
            "rewrite":    rewrite,
            "added_text": added["added"],
            "section":    match["section"],
            "score":      match["score"],
            "engine":     engine,
            "type":       "rewrite",
        })

    rewrites.sort(key=lambda r: r["score"], reverse=True)
    return rewrites


# ── Suggestion templates ───────────────────────────────────────────────────────

def _format_skills_suggestion(keywords: List[str]) -> str:
    kw_list = ", ".join(f"`{k}`" for k in keywords[:6])
    extra   = f" (+{len(keywords)-6} more)" if len(keywords) > 6 else ""
    return (
        f"Add these to your **Skills** section: {kw_list}{extra}. "
        f"List them exactly as they appear in the job posting — ATS systems match exact strings."
    )


def _format_experience_suggestion(keywords: List[str]) -> str:
    kw_list = ", ".join(f"`{k}`" for k in keywords[:5])
    extra   = f" (+{len(keywords)-5} more)" if len(keywords) > 5 else ""
    return (
        f"Weave into your **Experience** bullets: {kw_list}{extra}. "
        f"See the rewrite suggestions below for concrete examples — they target "
        f"the bullets in your resume that already touch these topics."
    )


def _format_summary_suggestion(keywords: List[str]) -> str:
    kw_list = ", ".join(f"`{k}`" for k in keywords[:4])
    first   = keywords[0] if keywords else "the required skill"
    second  = keywords[1] if len(keywords) > 1 else first
    return (
        f"Add to your **Professional Summary**: {kw_list}. "
        f'Example: *"Results-driven engineer with expertise in {first} and {second}."*'
    )


def _format_cert_suggestion(keywords: List[str]) -> str:
    kw_list = ", ".join(f"`{k}`" for k in keywords[:4])
    return (
        f"The job mentions: {kw_list}. "
        f"If you hold these credentials, add them to a **Certifications** section. "
        f"If not, consider if any are worth pursuing — they signal exactly what this employer wants."
    )


def _format_projects_suggestion(keywords: List[str]) -> str:
    kw_list = ", ".join(f"`{k}`" for k in keywords[:4])
    first   = keywords[0] if keywords else "this technology"
    return (
        f"Mention {kw_list} in a **Projects** entry. "
        f'Example: *"Built X using {first} — [GitHub link]."* '
        f"This shows hands-on experience even if it wasn't a paid role."
    )


_SECTION_FORMATTERS = {
    "skills":         _format_skills_suggestion,
    "experience":     _format_experience_suggestion,
    "summary":        _format_summary_suggestion,
    "certifications": _format_cert_suggestion,
    "projects":       _format_projects_suggestion,
}


# ── Main suggestion function ───────────────────────────────────────────────────

def _is_domain_mismatch(scan_result: Dict) -> bool:
    """
    Detect when the JD's keyword profile doesn't overlap with the resume's
    domain — i.e. the user is applying for a role outside their actual
    background (e.g. a Backend SDE applying to a Robotics Simulation job).

    Signals (all must hold):
      - ats_score is low (< 55)
      - keyword_score is very low (< 35)
      - semantic_score is also weak (< 65) — if semantic is high, the
        domains are related and just lack exact-keyword matches; if both
        are low, the resume is genuinely outside the JD's domain.
    """
    return (
        scan_result.get("ats_score", 100) < 55
        and scan_result.get("keyword_score", 100) < 35
        and scan_result.get("semantic_score", 100) < 65
    )


def generate_suggestions(scan_result: Dict) -> List[Dict]:
    """Generate prioritised, section-targeted improvement suggestions."""
    missing        = scan_result.get("missing_keywords", [])
    implied        = scan_result.get("implied_keywords", [])
    missing_by_sec = scan_result.get("missing_by_section", {})
    bullet_matches = scan_result.get("bullet_matches", {}) or {}
    ats_score      = scan_result.get("ats_score", 0)
    kw_score       = scan_result.get("keyword_score", 0)
    sem_score      = scan_result.get("semantic_score", 0)
    found          = scan_result.get("found_keywords", [])
    sections       = set(scan_result.get("resume_sections", []))

    suggestions: List[Dict] = []

    # ── 0a. Section-presence guidance (if a section is missing, suggesting
    #        "tweak your summary" doesn't work — tell the user to add it). ──
    if "summary" not in sections:
        suggestions.append({
            "priority": "high", "section": "Summary",
            "category": "Section Missing",
            "suggestion": (
                "**Your resume has no Summary section.** Add a 2-3 sentence "
                "Professional Summary at the top — it's the first thing ATS "
                "and recruiters read. Use the LLM-generated summary in the "
                "drawer below as a starting point if available."
            ),
        })
    if "projects" not in sections and ats_score < 70:
        suggestions.append({
            "priority": "medium", "section": "Projects",
            "category": "Section Missing",
            "suggestion": (
                "Consider adding a **Projects** section showing hands-on work "
                "with the missing technical skills below. Side projects, "
                "open-source contributions, or class projects all count — "
                "they let you legitimately add keywords without faking "
                "professional experience."
            ),
        })

    # ── 0. Domain mismatch — show FIRST, override everything else ─────────────
    # Critical guardrail: when the resume's domain doesn't overlap the JD's,
    # the user shouldn't be told to "weave robotics keywords into your
    # backend bullets" — that would be fabrication. Tell them honestly.
    if _is_domain_mismatch(scan_result):
        suggestions.append({
            "priority": "high", "section": "Overall",
            "category": "Role Fit",
            "suggestion": (
                f"**This role may not be a strong fit for your background "
                f"(match {ats_score:.0f}%).** The JD asks for skills your resume "
                f"doesn't currently show experience with — most missing keywords "
                f"aren't even semantically close to anything in your work history. "
                f"**Don't fabricate experience** to add these keywords. If you "
                f"genuinely have hands-on work with them (open-source, classes, "
                f"side projects), add it factually. Otherwise, consider whether "
                f"this role is worth the application time."
            ),
        })

    # ── 1. Overall alignment (skipped if domain-mismatch already covered it) ─
    if not _is_domain_mismatch(scan_result):
        if ats_score < 40:
            suggestions.append({
                "priority": "high", "section": "Overall",
                "category": "ATS Compatibility",
                "suggestion": (
                    f"**Low match ({ats_score:.0f}%).** Your resume is missing many of the key terms "
                    f"this employer's ATS will scan for. Focus on the missing keywords below — "
                    f"adding 5–6 of the right ones can jump your score by 20+ points."
                ),
            })
        elif ats_score < 65:
            suggestions.append({
                "priority": "medium", "section": "Overall",
                "category": "ATS Compatibility",
                "suggestion": (
                    f"**Moderate match ({ats_score:.0f}%).** You're in the right ballpark. "
                    f"Add the missing keywords below to push past 75%."
                ),
            })
        else:
            msg_extra = f" {len(implied)} more are implied semantically." if implied else ""
            suggestions.append({
                "priority": "low", "section": "Overall",
                "category": "ATS Compatibility",
                "suggestion": (
                    f"**Good match ({ats_score:.0f}%).** You're already hitting most key terms "
                    f"({len(found)} found).{msg_extra} Review the missing list below — only add "
                    f"keywords you can back up in an interview."
                ),
            })

    # ── 2. Section-targeted keyword suggestions ───────────────────────────────
    # Skills suggestions stay generic ("add these to Skills"). Experience
    # suggestions are toned down here — the concrete bullet rewrites below
    # (when present) carry the actual prose changes; these section pointers
    # tell the user WHICH bullets to look at.
    has_rewrites = bool(bullet_matches)

    for section, keywords in missing_by_sec.items():
        if not keywords:
            continue

        num_kw   = len(keywords)
        priority = "high" if num_kw >= 4 else "medium" if num_kw >= 2 else "low"
        category = _categorise(keywords)

        if section == "experience" and has_rewrites:
            # Don't push every missing keyword into Experience when only some
            # of them have a real bullet match. Tell the user what's coming.
            covered_kws   = [k for k in keywords if k in bullet_matches]
            uncovered_kws = [k for k in keywords if k not in bullet_matches]
            parts = []
            if covered_kws:
                parts.append(
                    f"For {', '.join(f'`{k}`' for k in covered_kws[:5])}"
                    + (f" (+{len(covered_kws)-5} more)" if len(covered_kws) > 5 else "")
                    + " — see the **bullet rewrites** below; each one shows a "
                    + "concrete before/after for one of your existing Experience bullets."
                )
            if uncovered_kws:
                parts.append(
                    f"For {', '.join(f'`{k}`' for k in uncovered_kws[:4])}"
                    + (f" (+{len(uncovered_kws)-4} more)" if len(uncovered_kws) > 4 else "")
                    + " — your resume has no closely-related bullet. Only add these "
                    + "if you genuinely have the experience, and add a NEW bullet "
                    + "rather than forcing them into an existing sentence."
                )
            suggestion_txt = "  \n".join(parts) if parts else _format_experience_suggestion(keywords)
        else:
            formatter      = _SECTION_FORMATTERS.get(section, _format_skills_suggestion)
            suggestion_txt = formatter(keywords)

        suggestions.append({
            "priority": priority,
            "section":  section.title(),
            "category": category,
            "suggestion": suggestion_txt,
        })

    # ── 3. Semantic gap (only when NOT a domain mismatch) ─────────────────────
    if sem_score < 45 and ats_score < 70 and not _is_domain_mismatch(scan_result):
        suggestions.append({
            "priority": "high", "section": "Summary",
            "category": "Topic Relevance",
            "suggestion": (
                "The **overall topic** of your resume doesn't closely match this job's domain. "
                "Rewrite your **Professional Summary** using the job's own language — "
                "mirror the role title, the core tech stack, and 2–3 most-repeated phrases "
                "from the job description (only ones you genuinely have experience with)."
            ),
        })

    # ── 4. Formatting tip (only if keyword score is very low AND not domain mismatch) ─
    if kw_score < 30 and not _is_domain_mismatch(scan_result):
        suggestions.append({
            "priority": "medium", "section": "Format",
            "category": "ATS Formatting",
            "suggestion": (
                "**ATS parsers struggle with complex formatting.** "
                "If your resume uses tables, text boxes, headers/footers, or columns, "
                "switch to a single-column plain-text layout. "
                "Keep your Skills section as a simple comma-separated list."
            ),
        })

    order = {"high": 0, "medium": 1, "low": 2}
    suggestions.sort(key=lambda s: order.get(s["priority"], 3))
    return suggestions
