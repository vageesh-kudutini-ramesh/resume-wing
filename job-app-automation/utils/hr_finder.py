"""
HR / Hiring Manager finder.
Generates smart LinkedIn search URLs and referral message templates.
100% free — no external API needed, pure URL construction.
"""
import urllib.parse
from typing import Dict, List


def get_linkedin_urls(company: str, job_title: str) -> Dict[str, str]:
    """
    Build LinkedIn People Search URLs for HR and Hiring Manager discovery.
    Returns a dict of {label: url}.
    """
    company_enc = urllib.parse.quote(company)
    title_enc   = urllib.parse.quote(job_title)

    # Derive the relevant manager title from the job title
    manager_title = _derive_manager_title(job_title)

    return {
        "Recruiter / HR":
            f"https://www.linkedin.com/search/results/people/"
            f"?keywords={urllib.parse.quote('recruiter OR HR OR talent acquisition')}%20{company_enc}"
            f"&origin=GLOBAL_SEARCH_HEADER",

        f"Hiring Manager ({manager_title})":
            f"https://www.linkedin.com/search/results/people/"
            f"?keywords={urllib.parse.quote(manager_title)}%20{company_enc}"
            f"&origin=GLOBAL_SEARCH_HEADER",

        "Company LinkedIn Page":
            f"https://www.linkedin.com/search/results/companies/"
            f"?keywords={company_enc}",
    }


def get_referral_templates(
    candidate_name: str,
    company: str,
    job_title: str,
    top_skills: List[str],
) -> Dict[str, str]:
    """
    Return ready-to-send LinkedIn connection request and referral message templates.
    """
    skills_str = ", ".join(top_skills[:3]) if top_skills else "the relevant skill set"

    connection_note = (
        f"Hi [Name], I noticed {company} is hiring for a {job_title}. "
        f"I have experience in {skills_str} and would love to learn more about the team. "
        f"Would you be open to connecting?"
    )

    referral_message = (
        f"Hi [Name],\n\n"
        f"I hope you're doing well! I came across the {job_title} opening at {company} "
        f"and I'm genuinely excited about it. I have experience in {skills_str} "
        f"and believe I'd be a strong fit.\n\n"
        f"Would you be able to refer me or share any insights about the role / team culture? "
        f"I'd really appreciate it!\n\n"
        f"Thanks so much,\n{candidate_name}"
    )

    cold_email = (
        f"Subject: {job_title} Role at {company} — Referral Request\n\n"
        f"Hi [Name],\n\n"
        f"I recently applied for the {job_title} position at {company} and I'm very excited "
        f"about the opportunity. I noticed you work at {company} and reached out hoping you "
        f"might be able to refer me or provide a warm introduction.\n\n"
        f"A bit about me: I bring experience in {skills_str} and have [X years] of "
        f"relevant industry experience.\n\n"
        f"I completely understand if you're not in a position to help, but any guidance "
        f"would be greatly appreciated.\n\n"
        f"Thank you for your time!\n{candidate_name}"
    )

    return {
        "LinkedIn Connection Note (280 chars)": connection_note,
        "LinkedIn Referral Message":            referral_message,
        "Cold Email / InMail Template":         cold_email,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _derive_manager_title(job_title: str) -> str:
    """Infer what a hiring manager's title might be for a given job title."""
    jt = job_title.lower()

    if any(x in jt for x in ["data scientist", "ml engineer", "machine learning"]):
        return "Head of Data OR Director of ML"
    if any(x in jt for x in ["data engineer", "data analyst"]):
        return "Director of Data Engineering OR VP of Data"
    if any(x in jt for x in ["frontend", "front-end", "ui engineer"]):
        return "Engineering Manager Frontend OR VP Engineering"
    if any(x in jt for x in ["backend", "back-end", "api engineer"]):
        return "Engineering Manager OR VP Engineering"
    if any(x in jt for x in ["full stack", "software engineer", "developer"]):
        return "Engineering Manager OR Director of Engineering"
    if any(x in jt for x in ["devops", "sre", "platform", "infrastructure"]):
        return "Director of Infrastructure OR VP Engineering"
    if any(x in jt for x in ["product manager", "pm "]):
        return "VP Product OR Director of Product"
    if any(x in jt for x in ["designer", "ux", "ui/ux"]):
        return "Head of Design OR Design Manager"
    if any(x in jt for x in ["qa", "quality", "test"]):
        return "QA Manager OR Director of Engineering"
    return "Engineering Manager OR Technical Manager"
