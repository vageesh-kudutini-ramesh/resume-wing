"""
Ollama client for the resume rewrite engine.

Why local Ollama instead of a cloud LLM:
  - Zero cost, no API keys to manage
  - Resume content never leaves the user's machine
  - Works fully offline once the model is pulled

The `generate()` function returns a string on success and None on any failure
(Ollama not running, model missing, timeout, network error). Callers MUST
treat None as "fall back to templates" — never surface an error to the user
just because the LLM is unavailable.

Caching:
  Rewrites are pure functions of (bullet, keyword, model). We cache them
  on disk in a JSON file so repeated scans of the same resume against the
  same JD don't pay the LLM cost twice.
"""
import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import requests

from config import (
    DATA_DIR,
    OLLAMA_MAX_PARALLEL,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT_SECONDS,
    OLLAMA_URL,
)


_CACHE_FILE = DATA_DIR / "rewrite_cache.json"
_CACHE_LOCK = threading.Lock()
_AVAILABLE_CACHE: Dict[str, Tuple[bool, float]] = {}  # url -> (ok, timestamp)
_AVAILABLE_TTL = 30.0  # re-check Ollama at most every 30 s


# ── Health check ───────────────────────────────────────────────────────────────

def is_available() -> bool:
    """
    Return True if Ollama is reachable AND the configured model is pulled.
    Cached for 30 s so we don't probe on every rewrite call.
    """
    now = time.time()
    cached = _AVAILABLE_CACHE.get(OLLAMA_URL)
    if cached and now - cached[1] < _AVAILABLE_TTL:
        return cached[0]

    ok = False
    try:
        # /api/tags returns the list of pulled models — fast (~5 ms locally)
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        if resp.ok:
            tags = resp.json().get("models", [])
            names = {m.get("name", "").split(":")[0] for m in tags}
            names.update(m.get("name", "") for m in tags)
            wanted = OLLAMA_MODEL.split(":")[0]
            ok = wanted in names or OLLAMA_MODEL in names
    except Exception:
        ok = False

    _AVAILABLE_CACHE[OLLAMA_URL] = (ok, now)
    return ok


# ── Disk cache ─────────────────────────────────────────────────────────────────

def _load_cache() -> Dict[str, str]:
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache: Dict[str, str]) -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass


def _cache_key(bullet: str, keyword: str, model: str) -> str:
    raw = f"{model}\x1f{keyword}\x1f{bullet}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


# ── Single generation ──────────────────────────────────────────────────────────

def generate(prompt: str, *, temperature: float = 0.3, max_tokens: int = 256) -> Optional[str]:
    """
    Call Ollama once. Returns the trimmed response string on success, None on any failure.

    Uses /api/generate with stream=False so we get the full response in one
    HTTP round-trip — simpler than streaming for a one-shot rewrite.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json=payload,
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
        if not resp.ok:
            return None
        text = resp.json().get("response", "")
        return text.strip() if text else None
    except Exception:
        return None


# ── Batch generation with caching + concurrency ────────────────────────────────

def generate_batch(
    items: List[Tuple[str, str]],  # list of (bullet, keyword)
    prompt_builder: Callable[[str, str], str],
    response_cleaner: Callable[[str, str, str], Optional[str]],
) -> Dict[Tuple[str, str], Optional[str]]:
    """
    Run `prompt_builder(bullet, keyword)` -> Ollama -> `response_cleaner(raw, bullet, keyword)`
    for many items in parallel, with caching.

    Returns: dict mapping each (bullet, keyword) to the cleaned rewrite,
    or to None if Ollama failed for that pair (caller should fall back).
    """
    if not items:
        return {}

    cache = _load_cache()
    results: Dict[Tuple[str, str], Optional[str]] = {}
    to_compute: List[Tuple[str, str]] = []

    # First pass — serve from cache
    for bullet, keyword in items:
        key = _cache_key(bullet, keyword, OLLAMA_MODEL)
        if key in cache:
            results[(bullet, keyword)] = cache[key]
        else:
            to_compute.append((bullet, keyword))

    if not to_compute:
        return results

    # Second pass — only call Ollama if it's available, otherwise mark None
    if not is_available():
        for pair in to_compute:
            results[pair] = None
        return results

    def _one(pair: Tuple[str, str]) -> Tuple[Tuple[str, str], Optional[str]]:
        bullet, keyword = pair
        prompt = prompt_builder(bullet, keyword)
        raw = generate(prompt)
        cleaned = response_cleaner(raw, bullet, keyword) if raw else None
        return pair, cleaned

    workers = max(1, min(OLLAMA_MAX_PARALLEL, len(to_compute)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(_one, pair) for pair in to_compute]
        for fut in as_completed(futures):
            try:
                pair, cleaned = fut.result()
            except Exception:
                continue
            results[pair] = cleaned
            if cleaned is not None:
                key = _cache_key(pair[0], pair[1], OLLAMA_MODEL)
                with _CACHE_LOCK:
                    cache[key] = cleaned

    # Persist cache after the batch
    with _CACHE_LOCK:
        _save_cache(cache)

    return results
