"""
ATS Scanner — NLP-grade keyword extraction and semantic similarity.

Three-tier extraction:
  Tier 1 — KeyBERT with our curated stopwords + tight thresholds.
            (top_n=15, diversity=0.7, min_score=0.45). Returns 1-3 word
            phrases that the BERT model considers core to the JD.
  Tier 2 — Curated skill vocabulary (~400 entries). Catches specific
            tools/frameworks KeyBERT may rank below 0.45.
  Tier 3 — Bigrams that appear ≥2 times. Pure statistical fallback when
            both KeyBERT and the vocab return very few results.

Three-tier "is the keyword already covered?" filter:
  - Literal match against the resume → keyword is FOUND.
  - Embedding cosine similarity to any resume bullet > 0.55 → keyword is
    IMPLIED (treated as found; no suggestion generated).
  - Embedding similarity ≤ 0.55 → keyword is MISSING. If similarity to its
    closest bullet is ≥ 0.45 we'll suggest a rewrite of that bullet;
    otherwise it gets a "add to Skills section" suggestion.

Scoring:
  60% — Keyword match: % of important JD terms covered by the resume
        (literal + implied).
  40% — Semantic similarity: overall conceptual alignment via sentence
        embeddings.
"""
import re
from functools import lru_cache
from typing import Dict, List, Optional, Set, Tuple

import numpy as np


# ── Cached model loader ────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_keybert():
    """Load KeyBERT once and cache it. Returns None if not installed."""
    try:
        from keybert import KeyBERT
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        return KeyBERT(model=model)
    except ImportError:
        return None
    except Exception:
        return None


# ── Comprehensive stopwords ────────────────────────────────────────────────────
# These are passed to KeyBERT directly so the BERT extractor never returns them
# or any phrase containing them. Kept as a frozen set for fast membership tests.

_STOP_LIST: List[str] = [
    # Articles / pronouns / connectives
    "a","an","the","and","or","but","in","on","at","to","for","of","with","as",
    "by","from","into","through","during","before","after","above","below","up",
    "down","out","off","over","under","again","further","then","once","per",
    "via","within","across","along","around","between","among","toward","upon",
    "i","you","we","they","he","she","it","our","your","their","its","my","his",
    "her","this","that","these","those","who","whom","which","what","where","when",
    "why","how","all","both","each","few","more","most","other","some","such",
    "is","are","was","were","be","been","being","have","has","had","do","does",
    "did","will","would","could","should","may","might","shall","can","get","got",
    # Generic action verbs that appear in every JD and aren't skills
    "use","used","make","made","take","give","keep","let","put","set","go","come",
    "include","including","work","works","working","worked","ensure","help","helps",
    "drive","drives","driving","build","builds","building","built","create","creates",
    "define","support","provides","provide","enables","enable","focus","focuses",
    "partner","partners","partnering","engage","engages","engaging","manage",
    "manages","managing","managed","lead","leads","leading","led","own","owns",
    "run","runs","running","serve","serves","serving","need","needs","report",
    "reports","reporting","participate","participates","develop","develops",
    "maintain","maintains","design","designs","implement","implements","deliver",
    "delivers","evaluate","evaluates","identify","identifies","defines",
    # Generic adjectives / adverbs
    "new","good","great","key","high","large","small","strong","highly","deeply",
    "fast","core","main","major","top","best","full","real","true","wide","deep",
    "hard","easy","well","also","very","just","too","only","even","much","many",
    "less","same","so","than","yet","still","ever",
    "often","always","never","sometimes","usually","typically","generally",
    "approximately","minimum","maximum","least","about","roughly",
    # JD boilerplate vocabulary — adding these here is what fixes the
    # "team member / job responsibilities" noise problem the user reported.
    "experience","experienced","year","years","role","position","job","career",
    "opportunity","team","teams","company","organization","business","industry",
    "candidate","candidates","applicant","employer","employee","hire","hiring",
    "apply","applying","application","resume","requirements","required","require",
    "preferred","prefer","plus","bonus","nice","ideal","must","ability","abilities",
    "knowledge","understanding","familiar","familiarity","background",
    "skill","skills","qualification","qualifications","responsibility","responsibilities",
    "duty","duties","function","functions","description","overview","summary",
    "example","etc","note","please","equal","opportunity","eoe","location","remote",
    "onsite","hybrid","time","part","contract","permanent","temporary","competitive",
    "salary","benefits","compensation","equity","stock","health","dental","vision",
    "looking","seeking","ideal","desire","desired","prefer","preferred",
    "join","joining","passionate","mission","vision","values","culture",
    "ability","able","capable","capability","capabilities",
    "etc","including","includes","include",
]
_STOP: Set[str] = set(_STOP_LIST)


# ── Curated tech vocabulary (Tier 2) ──────────────────────────────────────────
# This list deliberately excludes role titles ("backend", "frontend",
# "fullstack", "architecture") and non-skill descriptors ("leadership",
# "mentoring") that previously polluted suggestions. Those are tracked in
# _ROLE_DESCRIPTORS for use in resume categorisation only.

_KNOWN_SKILLS: Set[str] = {
    "python","java","javascript","typescript","golang","go","rust","c++","c#",
    "ruby","php","scala","kotlin","swift","r","matlab","bash","shell","perl",
    "haskell","elixir","dart","julia","react","angular","vue","nextjs","nuxt",
    "gatsby","svelte","html","css","sass","scss","tailwind","bootstrap","webpack",
    "vite","redux","graphql","rest","restful","soap","grpc","websocket","jwt","oauth",
    "django","flask","fastapi","spring","springboot","express","rails","laravel",
    "nestjs","nodejs","dotnet","asp.net","hibernate","celery",
    "aws","azure","gcp","ec2","s3","lambda","rds","dynamodb","cloudformation",
    "terraform","pulumi","ansible","chef","puppet","cloudwatch","iam",
    "eks","ecs","fargate","sagemaker","bigquery","dataflow","pubsub","gke",
    "sql","mysql","postgresql","postgres","sqlite","oracle","mssql","mongodb",
    "redis","elasticsearch","cassandra","neo4j","influxdb","couchdb","snowflake",
    "redshift","databricks","dbt","airflow","spark","hadoop","kafka","flink",
    "hive","presto","druid","docker","kubernetes","k8s","helm","istio","jenkins",
    "gitlab","github","bitbucket","ci/cd","cicd","devops","sre","linux","unix",
    "nginx","apache","prometheus","grafana","datadog","splunk","elk","vault",
    "consul","packer","sonarqube","argocd","fluxcd",
    "machine learning","deep learning","tensorflow","pytorch","keras","scikit-learn",
    "sklearn","nlp","llm","openai","huggingface","bert","gpt","transformers",
    "xgboost","lightgbm","pandas","numpy","scipy","matplotlib","seaborn",
    "reinforcement learning","computer vision","opencv","mlops","mlflow",
    "feature engineering","model deployment","embeddings","rag","langchain",
    "cybersecurity","soc","siem","vulnerability","penetration testing",
    "pentest","owasp","encryption","ssl","tls","saml","sso","zero trust",
    "microservices","serverless","event-driven","api","sdk","saas","paas","iaas",
    "distributed systems","high availability","scalability","fault tolerance","caching",
    "load balancing","message queue","pub/sub","cqrs","ddd","solid",
    "agile","scrum","kanban","tdd","bdd","lean","gitops",
    "sprint","backlog","jira","confluence","notion",
    "ios","android","react native","flutter","xcode",
    "etl","elt","data pipeline","data warehouse","data lake","data modeling",
    "tableau","power bi","looker","metabase","qlik",
    "selenium","cypress","jest","pytest","junit","testng","postman","jmeter",
    "unit test","integration test","load testing",
    "monitoring","logging","observability","alerting","tracing","jaeger",
    "http","tcp/ip","dns","ssh","xml","json","yaml","protobuf","avro","parquet",
}

# Role descriptors — used for categorisation only, never suggested as keywords.
_ROLE_DESCRIPTORS: Set[str] = {
    "backend","frontend","fullstack","full-stack","full stack","embedded","firmware",
    "architecture","architect",
}

# Tokens that, when present in an extracted phrase, mark it as a job title
# rather than a skill. KeyBERT loves to pull "Senior Backend Engineer" out of
# JD headings — we filter it out here so it never reaches the missing list.
_ROLE_TITLE_TOKENS: Set[str] = {
    "engineer","engineers","developer","developers","programmer","programmers",
    "manager","managers","architect","architects","lead","leads","senior","junior",
    "principal","staff","intern","associate","analyst","analysts",
    "specialist","specialists","consultant","consultants","scientist","scientists",
    "designer","designers","director","directors","head","officer","executive",
    "administrator","administrators","coordinator","coordinators",
}


def _looks_like_role_title(phrase: str) -> bool:
    """True if the phrase reads like a job title rather than a skill."""
    if not phrase:
        return False
    tokens = phrase.lower().split()
    for tok in tokens:
        if tok in _ROLE_TITLE_TOKENS or tok in _ROLE_DESCRIPTORS:
            return True
    # Catch hyphenated multi-word descriptors like "full-stack"
    joined = phrase.lower()
    for desc in _ROLE_DESCRIPTORS:
        if " " in desc or "-" in desc:
            if desc in joined:
                return True
    return False

_METHODOLOGY_TERMS = {
    "agile","scrum","kanban","tdd","bdd","sre","devops","gitops","lean",
    "sprint","backlog","standup","retrospective","jira","confluence","notion",
}
_SOFT_SKILL_TERMS = {
    "leadership","mentoring","mentorship","communication","collaboration",
    "cross-functional","stakeholder","ownership","accountability",
}
_CERT_TERMS = {
    "certified","certification","certificate","cka","ckad","cissp","pmp",
    "ccna","ccnp","aws certified","azure certified","gcp professional",
}

# ── Section heading detection ─────────────────────────────────────────────────

_SECTION_PATTERNS = {
    "summary":    re.compile(r"(summary|objective|profile|about me|professional summary|career objective)", re.I),
    "experience": re.compile(r"(experience|employment|work history|professional experience|career|positions?)", re.I),
    "skills":     re.compile(r"(skills?|technical skills?|competencies|expertise|technologies|proficiencies)", re.I),
    "education":  re.compile(r"(education|academic|degree|university|college|qualification)", re.I),
    "projects":   re.compile(r"(projects?|portfolio|personal projects?|side projects?)", re.I),
    "certifications": re.compile(r"(certif|credential|license|accreditation)", re.I),
}


# ── JD pre-cleaning ───────────────────────────────────────────────────────────

# Sentence-level patterns that match JD boilerplate. We rip these out before
# KeyBERT sees the text — that's what stops "equal opportunity employer" /
# "competitive salary" / "401k" from showing up as missing keywords.
_BOILERPLATE_PATTERNS = [
    re.compile(r"(?i)equal\s+opportunity\s+employer[^.]*\."),
    re.compile(r"(?i)we\s+(are|do\s+not)\s+discriminate[^.]*\."),
    re.compile(r"(?i)we\s+are\s+committed\s+to\s+(diversity|equity|inclusion)[^.]*\."),
    re.compile(r"(?i)reasonable\s+accommodation[^.]*\."),
    re.compile(r"(?i)without\s+regard\s+to[^.]*\."),
    re.compile(r"(?i)401\s*\(?k\)?[^.]*\."),
    re.compile(r"(?i)competitive\s+(salary|compensation|benefits|pay)[^.]*\."),
    re.compile(r"(?i)comprehensive\s+benefits[^.]*\."),
    re.compile(r"(?i)stock\s+options?[^.]*\."),
    re.compile(r"(?i)paid\s+time\s+off[^.]*\."),
    re.compile(r"(?i)pto\b[^.]*\."),
    re.compile(r"(?i)health\s+(insurance|coverage|benefits)[^.]*\."),
    re.compile(r"(?i)to\s+apply[,:]?\s+(please|kindly)[^.]*\."),
    re.compile(r"(?i)please\s+(send|submit|attach)[^.]*\."),
    re.compile(r"(?i)background\s+check[^.]*\."),
    re.compile(r"(?i)e[\-\s]?verify[^.]*\."),
]

# Section-level: when these markers appear we drop everything that follows
# until a blank line or another likely-content marker. Catches "About us:"
# blocks pasted at the top of the JD.
_BOILERPLATE_SECTION_HEADERS = re.compile(
    r"(?im)^\s*(about\s+us|about\s+the\s+company|who\s+we\s+are|our\s+mission|"
    r"benefits|perks|compensation|eeoc?\s+statement|equal\s+opportunity)\s*[:\-–]\s*$"
)


def _strip_html(text: str) -> str:
    """
    Strip HTML tags and decode common HTML entities from a JD.

    Many job-board APIs (Jooble, Arbeitnow, JSearch) return descriptions
    with raw HTML. Feeding that to KeyBERT produces nonsense n-grams like
    "ma data lifeblood" (from "Boston, **MA**...**Data** is the **lifeblood**")
    or "learn life klaviyo" (from "to **learn** more about **life** at **Klaviyo**").
    Cleaning HTML before extraction is the fix.
    """
    if not text:
        return ""
    # 1. Drop <script> and <style> blocks entirely
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style[^>]*>.*?</style>",  " ", text, flags=re.I | re.S)
    # 2. Replace block-level tags with newlines so paragraph breaks survive
    text = re.sub(r"</?(p|div|br|li|ul|ol|h[1-6]|tr|td|table)\b[^>]*>", "\n", text, flags=re.I)
    # 3. Strip all remaining tags
    text = re.sub(r"<[^>]+>", " ", text)
    # 4. Decode common HTML entities. Use html.unescape for the long tail
    #    (handles &nbsp;, &#x27;, &amp;, etc.)
    try:
        import html as _html
        text = _html.unescape(text)
    except Exception:
        pass
    # 5. Replace remaining non-breaking spaces and special whitespace
    text = text.replace("\xa0", " ").replace("​", "")
    return text


def _clean_jd(jd_text: str) -> str:
    """Strip HTML, boilerplate sentences, and section blocks from a JD."""
    if not jd_text:
        return ""

    # 0. Strip HTML before any other processing (fixes nonsense keywords from
    #    job-board APIs that return raw HTML, e.g. Jooble / JSearch).
    text = _strip_html(jd_text)

    # Drop section blocks following known boilerplate headers up to next blank line
    lines = text.splitlines()
    out: List[str] = []
    skipping = False
    for line in lines:
        if _BOILERPLATE_SECTION_HEADERS.match(line):
            skipping = True
            continue
        if skipping:
            if not line.strip():
                skipping = False
            continue
        out.append(line)
    text = "\n".join(out)

    # Drop boilerplate sentences anywhere in the text
    for pat in _BOILERPLATE_PATTERNS:
        text = pat.sub(" ", text)

    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── Keyword extraction ─────────────────────────────────────────────────────────

def _extract_with_keybert(text: str, top_n: int = 15) -> List[str]:
    """
    Tier 1: KeyBERT with our curated stop list and tight thresholds.

    Tuned for precision over recall — we'd rather miss a few keywords than
    flood the user with noise. The custom _STOP_LIST is what kills the
    'team member / job responsibilities' garbage that the previous
    `stop_words="english"` config let through.
    """
    kb = _get_keybert()
    if kb is None:
        return []
    try:
        keywords = kb.extract_keywords(
            text,
            keyphrase_ngram_range=(1, 3),
            stop_words=_STOP_LIST,
            use_mmr=True,
            diversity=0.7,
            top_n=top_n,
        )
        cleaned: List[str] = []
        for kw, score in keywords:
            kw = kw.lower().strip()
            if score < 0.45:
                continue
            if len(kw) <= 2:
                continue
            if kw in _STOP:
                continue
            # Reject phrases that are mostly stop words
            tokens = kw.split()
            content = [t for t in tokens if t not in _STOP]
            if not content:
                continue
            # Reject job-title phrases ("senior backend engineer", "data analyst", ...)
            if _looks_like_role_title(kw):
                continue
            cleaned.append(kw)
        return cleaned
    except Exception:
        return []


def _extract_with_vocabulary(text: str) -> List[str]:
    """Tier 2: match against curated tech vocabulary."""
    text_lower = text.lower()
    found: List[str] = []
    seen: set = set()
    for skill in sorted(_KNOWN_SKILLS, key=len, reverse=True):
        if skill in seen:
            continue
        pattern = r"\b" + re.escape(skill) + r"\b"
        if re.search(pattern, text_lower):
            found.append(skill)
            seen.add(skill)
    return found


def _extract_significant_bigrams(text: str) -> List[str]:
    """Tier 3: 2-word phrases that appear ≥2 times."""
    words = re.findall(r"\b[a-z][a-z0-9+#./]*\b", text.lower())
    clean = [w for w in words if w not in _STOP and len(w) > 2]
    freq: Dict[str, int] = {}
    for i in range(len(clean) - 1):
        bigram = f"{clean[i]} {clean[i+1]}"
        freq[bigram] = freq.get(bigram, 0) + 1
    return [b for b, c in sorted(freq.items(), key=lambda x: -x[1]) if c >= 2]


def _extract_jd_keywords(jd_text: str) -> List[str]:
    """Run all three tiers and return a deduplicated list of keywords."""
    seen: set = set()
    all_kw: List[str] = []

    kb_kw = _extract_with_keybert(jd_text, top_n=15)
    for kw in kb_kw:
        if kw not in seen and kw not in _STOP:
            all_kw.append(kw)
            seen.add(kw)

    for kw in _extract_with_vocabulary(jd_text):
        if kw not in seen:
            all_kw.append(kw)
            seen.add(kw)

    if len(all_kw) < 8:
        for bigram in _extract_significant_bigrams(jd_text):
            if bigram not in seen:
                all_kw.append(bigram)
                seen.add(bigram)
                if len(all_kw) >= 12:
                    break

    return all_kw


def _resume_keyword_set(resume_text: str) -> set:
    """Build the set of literal terms present in the resume."""
    text_lower = resume_text.lower()
    present: set = set()

    for skill in _KNOWN_SKILLS:
        pattern = r"\b" + re.escape(skill) + r"\b"
        if re.search(pattern, text_lower):
            present.add(skill)

    words = re.findall(r"\b[a-z][a-z0-9+#./]*\b", text_lower)
    clean = [w for w in words if w not in _STOP and len(w) > 2]
    for i in range(len(clean) - 1):
        present.add(f"{clean[i]} {clean[i+1]}")

    # Single content words too — so "kubernetes" matches even without bigram context
    for w in clean:
        present.add(w)

    return present


# ── Already-implied filter ─────────────────────────────────────────────────────

# Tuned empirically: 0.55 was too strict — "ci/cd" vs "Implemented CI pipelines
# in Jenkins" sits around 0.50, which is clearly a coverage match. 0.50 catches
# these synonym cases without flagging genuinely missing concepts as implied.
_IMPLIED_THRESHOLD = 0.50


def _filter_implied_keywords(
    missing: List[str],
    bullets: List[Dict[str, str]],
) -> Tuple[List[str], List[str]]:
    """
    Split `missing` into (truly_missing, implied_in_resume).

    A keyword is implied if at least one resume bullet's embedding has cosine
    similarity ≥ _IMPLIED_THRESHOLD with the keyword's embedding. This catches
    cases like JD says "Kubernetes" but resume says "K8s" / "container
    orchestration" — literal match fails, semantic match wins.
    """
    if not missing or not bullets:
        return missing, []

    try:
        from matching.embedder import encode_batch

        bullet_texts = [b["text"] for b in bullets]
        kw_queries = [
            f"experience with {kw}" if " " not in kw else f"experience with {kw}"
            for kw in missing
        ]

        all_embs = encode_batch(bullet_texts + kw_queries)
        b_embs = all_embs[:len(bullet_texts)]
        kw_embs = all_embs[len(bullet_texts):]

        truly_missing: List[str] = []
        implied: List[str] = []

        for i, kw in enumerate(missing):
            kw_emb = kw_embs[i]
            if kw_emb is None:
                truly_missing.append(kw)
                continue
            best = -1.0
            for b_emb in b_embs:
                if b_emb is None:
                    continue
                sim = float(np.dot(kw_emb, b_emb))
                if sim > best:
                    best = sim
            if best >= _IMPLIED_THRESHOLD:
                implied.append(kw)
            else:
                truly_missing.append(kw)

        return truly_missing, implied

    except Exception:
        return missing, []


# ── Scoring ────────────────────────────────────────────────────────────────────

def _keyword_score(
    resume_text: str,
    jd_text: str,
    bullets: Optional[List[Dict[str, str]]] = None,
) -> Tuple[float, List[str], List[str], List[str]]:
    """
    Returns (score, found, missing, implied).

    `found`   — literal matches in the resume.
    `implied` — keywords semantically covered (above _IMPLIED_THRESHOLD).
    `missing` — neither literal nor semantic match.
    Score is computed against (found ∪ implied), so the user gets credit for
    coverage that doesn't use the JD's exact wording.
    """
    jd_keywords  = _extract_jd_keywords(jd_text)
    resume_terms = _resume_keyword_set(resume_text)

    literal_found = [kw for kw in jd_keywords if kw in resume_terms]
    not_literal   = [kw for kw in jd_keywords if kw not in resume_terms]

    truly_missing, implied = _filter_implied_keywords(not_literal, bullets or [])

    if not jd_keywords:
        return 0.0, [], [], []

    covered = len(literal_found) + len(implied)
    score   = round(covered / len(jd_keywords) * 100, 1)
    return score, literal_found, truly_missing, implied


def _semantic_score(resume_text: str, jd_text: str) -> float:
    """Cosine similarity between resume and JD embeddings, 0–100 scale."""
    try:
        from matching.embedder import encode
        r_emb = encode(resume_text)
        j_emb = encode(jd_text)
        if r_emb is None or j_emb is None:
            return 0.0
        sim = float(np.dot(r_emb, j_emb))
        return round(max(0.0, min(100.0, (sim + 1) / 2 * 100)), 1)
    except Exception:
        return 0.0


# ── Resume section + bullet parsing ───────────────────────────────────────────

def parse_resume_sections(resume_text: str) -> Dict[str, str]:
    """Split the resume into {section_name: section_text}."""
    lines = resume_text.splitlines()
    sections: Dict[str, List[str]] = {"other": []}
    current = "other"
    for line in lines:
        stripped = line.strip()
        matched = None
        for name, pattern in _SECTION_PATTERNS.items():
            if pattern.search(stripped) and len(stripped) < 60:
                matched = name
                break
        if matched:
            current = matched
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(line)
    return {k: "\n".join(v) for k, v in sections.items() if v}


_CONTACT_RE  = re.compile(r"@|https?://|linkedin|github|\.com|\(\d{3}\)|\d{10}", re.I)
_DATE_RE     = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|20\d{2}|19\d{2})\b", re.I
)
_BULLET_MARKER = re.compile(r"^[•\-\*▪►→◦▶⦿⁃✓✔]\s*")


def parse_resume_bullets(resume_text: str) -> List[Dict[str, str]]:
    """
    Parse a resume into bullet points / sentences, tagged with parent section.

    Filtering rules:
      - >25 chars and ≥5 words (skips headings, dates, short labels)
      - Skips lines containing contact info (email, URL, phone)
      - Skips short date-only lines
      - Experience + Projects bullets returned first (richest for rewrites)
    """
    sections = parse_resume_sections(resume_text)

    section_priority = ["experience", "projects", "summary", "skills",
                        "education", "certifications", "other"]
    ordered = {s: sections[s] for s in section_priority if s in sections}
    for s, t in sections.items():
        if s not in ordered:
            ordered[s] = t

    bullets: List[Dict[str, str]] = []
    for section_name, section_text in ordered.items():
        for line in section_text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if _CONTACT_RE.search(stripped):
                continue
            if _DATE_RE.search(stripped) and len(stripped) < 60:
                continue
            clean = _BULLET_MARKER.sub("", stripped)
            if len(clean) > 25 and len(clean.split()) >= 5:
                bullets.append({"text": clean, "section": section_name})

    return bullets


# ── Semantic keyword → bullet matching ────────────────────────────────────────

# Threshold tuned by trial: 0.28 was too low (forced rewrites onto unrelated
# bullets), 0.45 was too strict (real keywords like "kubernetes" couldn't pair
# with bullets about "containerized microservices"). 0.38 lets reasonable
# pairings through; the LLM's own validation rejects forced rewrites where
# the keyword genuinely doesn't fit the bullet.
_BULLET_MATCH_THRESHOLD = 0.38


# Sections that can sensibly host a sentence-level rewrite. Skills lines are
# comma-separated lists — rewriting them as a bullet sentence destroys the
# format. Education and certifications are factual records; rewriting them
# would invent credentials. Only experience-style prose qualifies.
_REWRITABLE_SECTIONS = {"experience", "projects", "summary", "other"}


def match_keywords_to_bullets(
    missing_keywords: List[str],
    bullets: List[Dict[str, str]],
) -> Dict[str, Dict]:
    """
    For each missing keyword, find the resume bullet most semantically related
    to it. Only return matches above _BULLET_MATCH_THRESHOLD — weaker pairings
    produce ungrammatical rewrites and should become "add to Skills" instead.

    Only considers bullets from Experience / Projects / Summary / Other —
    Skills lines (`Languages: Java, Python, ...`), Education, and
    Certifications are excluded so the LLM never tries to rewrite them as
    a sentence.
    """
    if not bullets or not missing_keywords:
        return {}

    rewritable = [b for b in bullets if b.get("section") in _REWRITABLE_SECTIONS]
    if not rewritable:
        return {}

    try:
        from matching.embedder import encode_batch

        bullet_texts = [b["text"] for b in rewritable]
        kw_queries   = [
            f"implemented {kw}" if " " not in kw else f"experience with {kw}"
            for kw in missing_keywords
        ]

        all_embs = encode_batch(bullet_texts + kw_queries)
        b_embs   = all_embs[:len(bullet_texts)]
        kw_embs  = all_embs[len(bullet_texts):]

        results: Dict[str, Dict] = {}
        for i, kw in enumerate(missing_keywords):
            kw_emb = kw_embs[i]
            if kw_emb is None:
                continue

            best_score  = -1.0
            best_bullet: Optional[Dict[str, str]] = None

            for j, b_emb in enumerate(b_embs):
                if b_emb is None:
                    continue
                sim = float(np.dot(kw_emb, b_emb))
                if sim > best_score:
                    best_score  = sim
                    best_bullet = rewritable[j]

            if best_bullet and best_score >= _BULLET_MATCH_THRESHOLD:
                results[kw] = {
                    "bullet_text": best_bullet["text"],
                    "section":     best_bullet["section"],
                    "score":       round(best_score, 3),
                }

        return results

    except Exception:
        return {}


def _assign_section(keyword: str) -> str:
    kw = keyword.lower()
    if any(t in kw for t in _CERT_TERMS):
        return "certifications"
    if kw in _SOFT_SKILL_TERMS or any(t in kw for t in _SOFT_SKILL_TERMS):
        return "summary"
    if kw in _METHODOLOGY_TERMS or any(t in kw for t in _METHODOLOGY_TERMS):
        return "experience"
    if " " in keyword:
        return "experience"
    return "skills"


# ── Main entry ─────────────────────────────────────────────────────────────────

def run_ats_scan(resume_text: str, job_description: str) -> Dict:
    """Full ATS scan. Returns scores, found/missing/implied, sections, bullet matches."""
    cleaned_jd = _clean_jd(job_description)
    bullets    = parse_resume_bullets(resume_text)

    kw_score, found, missing, implied = _keyword_score(resume_text, cleaned_jd, bullets)
    sem_score = _semantic_score(resume_text, cleaned_jd)
    combined  = round(kw_score * 0.6 + sem_score * 0.4, 1)

    resume_sections = parse_resume_sections(resume_text)
    missing_by_section: Dict[str, List[str]] = {}
    for kw in missing:
        section = _assign_section(kw)
        missing_by_section.setdefault(section, []).append(kw)

    bullet_matches = match_keywords_to_bullets(missing, bullets)

    keybert_available = _get_keybert() is not None

    return {
        "ats_score":           combined,
        "keyword_score":       kw_score,
        "semantic_score":      sem_score,
        "found_keywords":      sorted(found),
        "implied_keywords":    sorted(implied),
        "missing_keywords":    sorted(missing),
        "resume_sections":     list(resume_sections.keys()),
        "missing_by_section":  missing_by_section,
        "bullet_matches":      bullet_matches,
        "nlp_mode":            "keybert" if keybert_available else "vocabulary",
    }
