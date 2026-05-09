"""
Phase-1 verification harness for the ATS scanner + rewrite engine.

Run from the job-app-automation/ directory:

    .\\venv\\Scripts\\python -m ats._verify

What it does:
  1. Reports whether Ollama is reachable and the configured model is pulled
  2. Runs run_ats_scan() against a sample resume/JD pair
  3. Prints found / implied / missing keywords
  4. Prints each rewrite with its engine tag (llm vs template) so you can
     visually confirm the LLM is actually producing natural sentences.

This is a developer harness, not part of the production code path.
"""
import json
import sys
import time

from ats import llm_client
from ats.scanner import run_ats_scan, _clean_jd
from ats.suggestions import generate_bullet_rewrites, generate_suggestions


SAMPLE_RESUME = """\
JOHN DOE
john.doe@example.com | (555) 123-4567 | github.com/johndoe

PROFESSIONAL SUMMARY
Software engineer with 4 years of experience building scalable web services and data pipelines.

EXPERIENCE
Senior Software Engineer, Acme Corp · Jan 2022 - Present
- Built and shipped a payment processing service handling 10M transactions per day in Python and Go
- Designed and operated containerized microservices on AWS with multi-region failover
- Led migration of monolithic codebase to microservices, reducing deployment time by 60%
- Mentored 3 junior engineers through quarterly review process

Software Engineer, BetaSoft · Jun 2020 - Dec 2021
- Developed REST APIs in Django serving a mobile app with 500K monthly active users
- Implemented CI pipelines in Jenkins that reduced manual deployment errors by 80%
- Wrote unit and integration tests covering 75% of the codebase

EDUCATION
B.S. Computer Science, State University, 2020

SKILLS
Python, Go, Django, REST APIs, AWS, PostgreSQL, Jenkins, Git, Linux
"""

SAMPLE_JD = """\
Senior Backend Engineer

About Us:
We are an innovative fintech company building the future of payments. We are
committed to diversity, equity, and inclusion. We are an equal opportunity employer.

Job Description:
We are looking for a Senior Backend Engineer to join our growing team. You will
work on our core payment platform, building scalable services that process
billions of dollars in transactions annually.

Responsibilities:
- Design and implement microservices in Python or Go
- Build and operate Kubernetes clusters running on AWS EKS
- Implement CI/CD pipelines using GitHub Actions and Terraform
- Build observability with Prometheus and Grafana for monitoring service health
- Use PostgreSQL and Redis for transactional and caching workloads
- Mentor junior engineers and drive technical roadmap

Required Qualifications:
- 5+ years of backend engineering experience
- Strong Python or Go skills
- Hands-on Kubernetes experience
- Experience with PostgreSQL, Redis, and Kafka
- Familiarity with Terraform and infrastructure-as-code
- Strong communication skills and ownership

Nice to Have:
- Experience with gRPC
- Background in payment systems or financial services
- Open-source contributions

Benefits:
- Competitive salary and equity
- Comprehensive health, dental, vision insurance
- 401(k) matching
- Generous PTO
- Remote-friendly

To apply, please submit your resume and a cover letter.
"""


def _h(title: str) -> None:
    print()
    print("=" * 78)
    print(f"  {title}")
    print("=" * 78)


def main() -> int:
    _h("Ollama health check")
    available = llm_client.is_available()
    print(f"  Ollama URL:      {llm_client.OLLAMA_URL}")
    print(f"  Configured model: {llm_client.OLLAMA_MODEL}")
    print(f"  Reachable:        {available}")
    if not available:
        print("  → Rewrites will use the template fallback path.")
        print("  → To get LLM-powered rewrites: install Ollama, run")
        print(f"      `ollama pull {llm_client.OLLAMA_MODEL}`,")
        print("      then start the Ollama service.")

    _h("JD pre-cleaning")
    cleaned = _clean_jd(SAMPLE_JD)
    print(f"  Original length: {len(SAMPLE_JD)} chars")
    print(f"  Cleaned length:  {len(cleaned)} chars")
    print(f"  (Removed: EEO statement, About Us block, Benefits, application instructions.)")

    _h("Running scan")
    t0 = time.time()
    result = run_ats_scan(SAMPLE_RESUME, SAMPLE_JD)
    t1 = time.time()
    print(f"  Scan time:       {t1-t0:.2f}s")
    print(f"  ATS score:       {result['ats_score']}")
    print(f"  Keyword score:   {result['keyword_score']}")
    print(f"  Semantic score:  {result['semantic_score']}")
    print(f"  NLP mode:        {result['nlp_mode']}")
    print()
    print(f"  Found ({len(result['found_keywords'])}):")
    for kw in result["found_keywords"]:
        print(f"    + {kw}")
    print()
    print(f"  Implied ({len(result.get('implied_keywords', []))}):")
    for kw in result.get("implied_keywords", []):
        print(f"    ~ {kw}")
    print()
    print(f"  Missing ({len(result['missing_keywords'])}):")
    for kw in result["missing_keywords"]:
        print(f"    - {kw}")

    _h("Bullet rewrites")
    t0 = time.time()
    rewrites = generate_bullet_rewrites(result.get("bullet_matches", {}))
    t1 = time.time()
    print(f"  Rewrite time:    {t1-t0:.2f}s ({len(rewrites)} rewrites)")
    print()
    for rw in rewrites:
        marker = "[LLM]" if rw["engine"] == "llm" else "[template]"
        print(f"  {marker} keyword: {rw['keyword']}  (similarity: {rw['score']})")
        print(f"    BEFORE: {rw['original']}")
        print(f"    AFTER:  {rw['rewrite']}")
        print()

    _h("Section suggestions")
    suggestions = generate_suggestions(result)
    for s in suggestions:
        print(f"  [{s['priority']}] {s['section']} / {s['category']}")
        print(f"    {s['suggestion']}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
