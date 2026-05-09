/**
 * ResumeWing Autofill — Background Service Worker
 *
 * Responsibilities
 * ────────────────
 * 1. Fetch and cache the autofill profile from the local ResumeWing backend.
 * 2. Fetch and cache the remote ATS selector config from GitHub (so selector
 *    fixes go live immediately without reinstalling the extension).
 * 3. Respond to messages from content scripts with the cached data.
 *
 * Cache strategy
 * ──────────────
 * Profile:   refreshed on every install/startup, and on explicit request.
 *            Stale if > 5 min old (refreshed on next content script request).
 * Selectors: refreshed once per browser session (cached in storage).
 *            Falls back to the local ats-selectors.json if GitHub is unreachable.
 *
 * Why service worker?
 * ───────────────────
 * MV3 requires service workers instead of background pages. They can be
 * terminated at any time by the browser; all persistent state lives in
 * chrome.storage.local, never in module-level variables.
 */

'use strict';

// ── Configuration ─────────────────────────────────────────────────────────────

const BACKEND_URL        = 'http://localhost:8000/profile/autofill';
const RESUME_FILE_URL    = 'http://localhost:8000/resume/file';
const CACHE_TTL_MS       = 5 * 60 * 1000; // 5 minutes

/**
 * Selector and field-pattern config files are loaded from the extension's own
 * bundle. The previous design fetched them from GitHub so selector fixes
 * could roll out without re-installing the extension; we removed that path
 * because (a) no public repo is currently hosting them, and (b) the local
 * files are already version-controlled with the extension itself, so the
 * remote config added complexity without delivering value.
 *
 * If you ever want a remote-config feature back, the old flow lived at
 * commit ~3a0fd. Reintroduce by setting these URLs and removing the local
 * fallback short-circuit in fetchSelectors() / fetchFieldPatterns().
 */


// ── Profile fetching ──────────────────────────────────────────────────────────

async function fetchProfile() {
  try {
    const res = await fetch(BACKEND_URL, {
      cache:   'no-store',
      headers: { 'Accept': 'application/json' },
    });
    if (!res.ok) throw new Error(`Backend returned HTTP ${res.status}`);

    const profile = await res.json();
    await chrome.storage.local.set({
      rw_profile:    profile,
      rw_profile_ts: Date.now(),
      rw_error:      null,
    });
    return { profile, error: null };

  } catch (err) {
    const msg = err.message.includes('Failed to fetch')
      ? 'ResumeWing backend is offline. Run START.bat from the project root folder to start all services.'
      : err.message;

    await chrome.storage.local.set({ rw_error: msg });
    return { profile: null, error: msg };
  }
}


// ── Resume file fetching ──────────────────────────────────────────────────────

/**
 * Fetch the user's uploaded resume bytes from the backend and return them as
 * a base64 string — content scripts decode it back to bytes and feed it to
 * RW.fillFile() which uses the DataTransfer API to populate a file input.
 *
 * Returns: { ok, base64, filename, mimeType, error }
 */
async function fetchResumeFile() {
  try {
    const res = await fetch(RESUME_FILE_URL, { cache: 'no-store' });
    if (!res.ok) {
      const detail = await res.text().catch(() => '');
      return { ok: false, error: `Backend HTTP ${res.status}: ${detail.slice(0, 200)}` };
    }

    const buf = await res.arrayBuffer();
    // Convert ArrayBuffer → base64 in chunks (avoids "argument list too long"
    // when calling String.fromCharCode on a large typed array)
    const bytes = new Uint8Array(buf);
    let binary = '';
    const CHUNK = 0x8000;
    for (let i = 0; i < bytes.length; i += CHUNK) {
      binary += String.fromCharCode.apply(
        null, bytes.subarray(i, Math.min(i + CHUNK, bytes.length))
      );
    }
    const base64 = btoa(binary);

    // Pull filename from Content-Disposition; mimeType from Content-Type
    const disposition = res.headers.get('content-disposition') || '';
    const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
    const filename = m ? decodeURIComponent(m[1]) : 'resume.pdf';
    const mimeType = res.headers.get('content-type') || 'application/pdf';

    return { ok: true, base64, filename, mimeType };
  } catch (err) {
    const offline = (err.message || '').includes('Failed to fetch');
    return {
      ok: false,
      error: offline
        ? 'Backend offline — start the FastAPI server (uvicorn main:app --port 8000).'
        : err.message,
    };
  }
}


// ── Selector / field-pattern config loading ──────────────────────────────────

async function fetchSelectors() {
  return _loadLocalJSON('ats-selectors.json', 'rw_selectors');
}

async function fetchFieldPatterns() {
  return _loadLocalJSON('field-patterns.json', 'rw_field_patterns');
}

/**
 * Read a JSON file bundled with the extension and cache it in chrome.storage.local.
 * Returns an empty object if the file is missing or malformed — the rest of
 * the extension treats an empty config as "use built-in defaults".
 */
async function _loadLocalJSON(filename, storageKey) {
  try {
    const res = await fetch(chrome.runtime.getURL(filename));
    const data = await res.json();
    await chrome.storage.local.set({ [storageKey]: data });
    return data;
  } catch (_) {
    return {};
  }
}


// ── Startup hooks ─────────────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(async () => {
  await fetchProfile();
  await fetchSelectors();
  await fetchFieldPatterns();
});

chrome.runtime.onStartup.addListener(async () => {
  await fetchProfile();
  // Selectors and field patterns are bundled with the extension — re-load on
  // every browser start so any changes shipped in a new extension version
  // take effect without manually clearing chrome.storage.
  await fetchSelectors();
  await fetchFieldPatterns();
});


// ── Message handler (content scripts talk to us here) ─────────────────────────

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {

  // Content script asks for cached profile + selectors on page load
  if (msg.type === 'GET_DATA') {
    (async () => {
      const {
        rw_profile,
        rw_profile_ts,
        rw_selectors,
        rw_error,
      } = await chrome.storage.local.get([
        'rw_profile', 'rw_profile_ts', 'rw_selectors', 'rw_error',
      ]);

      // Auto-refresh if cache is stale
      const age     = Date.now() - (rw_profile_ts || 0);
      const isStale = age > CACHE_TTL_MS;

      if (isStale || !rw_profile) {
        const { profile, error } = await fetchProfile();
        const selectors = rw_selectors ?? await fetchSelectors();
        sendResponse({ profile, selectors, error });
      } else {
        const selectors = rw_selectors ?? await fetchSelectors();
        sendResponse({ profile: rw_profile, selectors, error: rw_error });
      }
    })();
    return true;  // Keep port open for async response
  }

  // User manually clicks "Refresh" in the panel
  if (msg.type === 'REFRESH_PROFILE') {
    fetchProfile().then(({ profile, error }) => sendResponse({ profile, error }));
    return true;
  }

  // Content script asks for the resume file bytes for DataTransfer-based
  // upload into a job site's <input type="file">.
  if (msg.type === 'FETCH_RESUME_FILE') {
    fetchResumeFile().then(sendResponse);
    return true;
  }

  // Universal classifier: get domain memory + field patterns in one call
  if (msg.type === 'GET_UNIVERSAL_DATA') {
    (async () => {
      const { rw_domain_mappings = {}, rw_field_patterns = {} } =
        await chrome.storage.local.get(['rw_domain_mappings', 'rw_field_patterns']);
      sendResponse({
        domainMemory:  rw_domain_mappings[msg.domain] ?? {},
        fieldPatterns: rw_field_patterns,
      });
    })();
    return true;
  }

  // Learn a confirmed field mapping for a domain (persists across sessions)
  if (msg.type === 'LEARN_MAPPING') {
    (async () => {
      const { rw_domain_mappings = {} } =
        await chrome.storage.local.get('rw_domain_mappings');
      if (!rw_domain_mappings[msg.domain]) rw_domain_mappings[msg.domain] = {};
      rw_domain_mappings[msg.domain][msg.selector] = msg.fieldKey;
      await chrome.storage.local.set({ rw_domain_mappings });
      sendResponse({ ok: true });
    })();
    return true;
  }

  // Forget learned mappings for a domain (for debugging / reset)
  if (msg.type === 'FORGET_DOMAIN') {
    (async () => {
      const { rw_domain_mappings = {} } =
        await chrome.storage.local.get('rw_domain_mappings');
      delete rw_domain_mappings[msg.domain];
      await chrome.storage.local.set({ rw_domain_mappings });
      sendResponse({ ok: true });
    })();
    return true;
  }
});
