"""
AI match scoring: cosine similarity between resume and job description embeddings.
Score is returned as 0–100 float.
"""
from typing import List, Tuple
import numpy as np

from database.models import Job
from matching.embedder import encode, encode_batch


def score_job(resume_text: str, job_description: str) -> float:
    """
    Return match score (0–100) between resume and a single job description.
    Uses cosine similarity on sentence-transformer embeddings.
    """
    resume_emb = encode(resume_text)
    job_emb = encode(job_description)

    if resume_emb is None or job_emb is None:
        return 0.0

    # Vectors are already L2-normalised by encode()
    similarity = float(np.dot(resume_emb, job_emb))
    # similarity is in [-1, 1]; map to [0, 100]
    score = max(0.0, min(100.0, (similarity + 1) / 2 * 100))
    return round(score, 1)


def score_jobs_batch(
    resume_text: str,
    jobs: List[Job],
    progress_callback=None,
) -> List[Tuple[Job, float]]:
    """
    Score a list of jobs against the resume in one batch pass.
    Returns list of (job, score) tuples sorted by score descending.
    """
    if not jobs or not resume_text:
        return []

    resume_emb = encode(resume_text)
    if resume_emb is None:
        return [(j, 0.0) for j in jobs]

    descriptions = [
        f"{j.title} {j.company} {j.description}" for j in jobs
    ]

    if progress_callback:
        progress_callback("🤖 Running AI matching...")

    job_embeddings = encode_batch(descriptions)
    results = []

    for job, job_emb in zip(jobs, job_embeddings):
        if job_emb is None:
            results.append((job, 0.0))
        else:
            sim = float(np.dot(resume_emb, job_emb))
            score = round(max(0.0, min(100.0, (sim + 1) / 2 * 100)), 1)
            results.append((job, score))

    results.sort(key=lambda x: x[1], reverse=True)
    return results
