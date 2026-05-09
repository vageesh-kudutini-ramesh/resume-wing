/**
 * ResumeWing Autofill — Content Script (Panel + Orchestrator)
 *
 * Load order guaranteed by manifest.json:
 *   1. ats/common.js   → sets up window.ResumeWingATS namespace + utilities
 *   2. ats/<platform>  → registers window.ResumeWingATS.module = { name, fill, detect }
 *   3. content.js      → THIS FILE — injects the UI and orchestrates the fill
 *
 * Responsibilities
 * ────────────────
 * - Inject the floating panel into the host page once (idempotent guard).
 * - Request the cached autofill profile + selectors from background.js.
 * - On "Fill" button click, call RW.module.fill(profile, atsSelectors).
 * - Render results (filled / skipped / error) back into the panel.
 */

(function () {
  'use strict';

  console.log('[ResumeWing] content.js injected on:', location.href);

  // ── Guard: inject only once ───────────────────────────────────────────────
  if (document.getElementById('rw-panel')) return;

  const RW = window.ResumeWingATS;
  if (!RW) { console.warn('[ResumeWing] content.js: ResumeWingATS missing — common.js failed?'); return; }

  const atsName = RW.module?.name ?? 'Unknown';

  // ── Build panel HTML ──────────────────────────────────────────────────────

  const ICON_SVG = `
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
         stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 2L2 7l10 5 10-5-10-5z"/>
      <path d="M2 17l10 5 10-5"/>
      <path d="M2 12l10 5 10-5"/>
    </svg>`;

  const container = document.createElement('div');
  container.id    = 'rw-panel';
  container.innerHTML = `
    <div id="rw-card">

      <div class="rw-header">
        <span class="rw-header-icon">${ICON_SVG}</span>
        <div class="rw-header-text">
          <div class="rw-logo">ResumeWing</div>
          <div class="rw-tagline">Auto-fill job application</div>
        </div>
        <button class="rw-header-close" id="rw-close" title="Minimize panel">✕</button>
      </div>

      <div id="rw-profile-section" style="display:none">
        <div class="rw-profile-name" id="rw-name">Loading profile…</div>
        <div class="rw-profile-meta" id="rw-meta"></div>
        <span class="rw-ats-badge" id="rw-ats-badge"></span>
      </div>

      <div class="rw-actions">
        <button id="rw-fill-btn" disabled>
          <span id="rw-btn-icon"></span>
          <span id="rw-btn-text">Loading…</span>
        </button>
        <span class="rw-refresh-link" id="rw-refresh">↺ Refresh profile</span>
      </div>

      <div id="rw-status"></div>

    </div>

    <button id="rw-toggle" title="ResumeWing Autofill">
      ${ICON_SVG}
    </button>`;

  document.body.appendChild(container);

  // ── Element refs ──────────────────────────────────────────────────────────

  const card           = document.getElementById('rw-card');
  const toggle         = document.getElementById('rw-toggle');
  const closeBtn       = document.getElementById('rw-close');
  const profileSection = document.getElementById('rw-profile-section');
  const nameEl         = document.getElementById('rw-name');
  const metaEl         = document.getElementById('rw-meta');
  const badgeEl        = document.getElementById('rw-ats-badge');
  const fillBtn        = document.getElementById('rw-fill-btn');
  const btnIcon        = document.getElementById('rw-btn-icon');
  const btnText        = document.getElementById('rw-btn-text');
  const statusEl       = document.getElementById('rw-status');
  const refreshLink    = document.getElementById('rw-refresh');

  let profile   = null;
  let selectors = {};

  // ── Panel open/close ──────────────────────────────────────────────────────

  function openPanel () {
    card.classList.add('rw-visible');
    toggle.style.display = 'none';
  }
  function closePanel () {
    card.classList.remove('rw-visible');
    toggle.style.display = 'flex';
  }

  toggle.addEventListener('click',  openPanel);
  closeBtn.addEventListener('click', closePanel);

  // ── Load profile from background ──────────────────────────────────────────

  function loadProfile (forceRefresh = false) {
    setBtnState('loading', 'Loading…');

    chrome.runtime.sendMessage(
      { type: forceRefresh ? 'REFRESH_PROFILE' : 'GET_DATA' },
      (resp) => {
        if (chrome.runtime.lastError || !resp) {
          showBackendOffline();
          return;
        }

        const { profile: p, selectors: s, error } = resp;

        if (error || !p) {
          showProfileError(error ?? 'No resume found — upload one in ResumeWing.');
          return;
        }

        profile   = p;
        selectors = s ?? {};
        renderProfile(p);
      }
    );
  }

  // ── Render profile info into the panel ───────────────────────────────────

  function renderProfile (p) {
    const fullName = [p.personal.first_name, p.personal.last_name]
      .filter(Boolean).join(' ') || 'Profile loaded';

    nameEl.textContent  = fullName;
    metaEl.textContent  = [
      p.personal.email,
      p.metadata.years_experience > 0
        ? `${p.metadata.years_experience} yrs exp`
        : '',
    ].filter(Boolean).join(' · ');
    badgeEl.textContent = `ATS: ${atsName}`;

    profileSection.style.display = 'block';
    setBtnState('ready', '⚡ Fill with ResumeWing');
  }

  // ── Error states ──────────────────────────────────────────────────────────

  function showBackendOffline () {
    nameEl.textContent           = 'Backend offline';
    metaEl.textContent           = 'Run START.bat from the project root folder.';
    profileSection.style.display = 'block';
    setBtnState('error', 'Backend not running');
    openPanel();
  }

  function showProfileError (msg) {
    nameEl.textContent           = msg;
    metaEl.textContent           = '';
    profileSection.style.display = 'block';
    setBtnState('error', 'No profile available');
    openPanel();
  }

  // ── Button state helper ───────────────────────────────────────────────────

  function setBtnState (state, label) {
    fillBtn.disabled = state !== 'ready';
    btnText.textContent = label;

    if (state === 'loading') {
      btnIcon.innerHTML = '<span class="rw-spinner"></span>';
    } else if (state === 'filling') {
      btnIcon.innerHTML = '<span class="rw-spinner"></span>';
    } else {
      btnIcon.innerHTML = '';
    }
  }

  // ── Resume file upload via DataTransfer ───────────────────────────────────

  /**
   * Try to auto-attach the user's resume PDF to a file input on this page.
   *
   * Returns one of:
   *   { status: 'uploaded',  filename }       — success
   *   { status: 'no_input' }                  — page has no resume file input
   *   { status: 'no_resume' }                 — backend has no file bytes
   *   { status: 'unsupported', reason }       — DataTransfer rejected (custom picker)
   *   { status: 'fetch_failed', error }       — backend fetch failed
   */
  async function attemptResumeUpload () {
    const input = RW.findResumeFileInput?.();
    if (!input) return { status: 'no_input' };

    const resp = await new Promise(resolve => {
      chrome.runtime.sendMessage({ type: 'FETCH_RESUME_FILE' }, resolve);
    });

    if (!resp || !resp.ok) {
      const err = resp?.error || 'unknown';
      if (/no resume uploaded/i.test(err) || /file bytes are missing/i.test(err)) {
        return { status: 'no_resume' };
      }
      return { status: 'fetch_failed', error: err };
    }

    // Decode base64 → Uint8Array (the bytes we'll wrap in a File object)
    let bytes;
    try {
      const binary = atob(resp.base64);
      bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    } catch (err) {
      return { status: 'fetch_failed', error: 'Failed to decode resume bytes' };
    }

    const ok = RW.fillFile(input, bytes, resp.filename, resp.mimeType);
    if (!ok) {
      return {
        status: 'unsupported',
        reason: 'This site uses a custom file picker that the extension cannot drive. Please attach the resume manually.',
      };
    }

    RW.highlight(input);
    return { status: 'uploaded', filename: resp.filename };
  }


  // ── Fill button handler ───────────────────────────────────────────────────

  fillBtn.addEventListener('click', async () => {
    if (!profile || !RW.module) return;

    setBtnState('filling', 'Filling…');
    statusEl.innerHTML = '';
    statusEl.classList.remove('rw-visible');

    // Pre-flight: if the current DOM has no fillable inputs at all, the user
    // probably hasn't opened the apply modal yet. Tell them what to do.
    const hasInputs = typeof RW.module.detect === 'function'
      ? RW.module.detect()
      : true;
    if (!hasInputs) {
      statusEl.innerHTML = `
        <div class="rw-error-banner">
          No form fields detected on this page yet.<br>
          If the application form is inside a popup or wizard, open it first
          (e.g. click the site's "Apply" or "Easy Apply" button) — then click
          Fill again.
        </div>`;
      statusEl.classList.add('rw-visible');
      setBtnState('ready', '↺ Try again');
      return;
    }

    let uploadResult = { status: 'no_input' };
    let fillResults = null;
    let fillError = null;

    try {
      // 1. Try to auto-attach the resume PDF (DataTransfer API)
      uploadResult = await attemptResumeUpload();

      // 2. Run the field-fill module (fills text/select/etc.)
      const atsOverrides = selectors[atsName.toLowerCase()] ?? {};
      fillResults = await RW.module.fill(profile, atsOverrides);

      // 3. Smart autofill pass — fills application questions (radios, "Why
      //    are you interested in X?" textareas, work authorization, etc.)
      //    that the platform module doesn't handle. Marks everything as
      //    "verify" yellow so the user reviews before submitting.
      if (typeof RW.smartAutofill === 'function') {
        try {
          await RW.smartAutofill(profile, fillResults);
        } catch (err) {
          console.warn('[ResumeWing] smartAutofill failed:', err);
        }
      }
    } catch (err) {
      fillError = err;
    }

    if (fillError) {
      statusEl.innerHTML =
        `<div class="rw-error-banner">Error during fill: ${fillError.message}</div>`;
      statusEl.classList.add('rw-visible');
    } else {
      renderResults(fillResults || { filled: [], skipped: [], errors: [] }, uploadResult);
    }

    setBtnState('ready', '↺ Fill again');
  });

  // ── Refresh link ──────────────────────────────────────────────────────────

  refreshLink.addEventListener('click', () => loadProfile(true));

  // ── Results renderer ──────────────────────────────────────────────────────
  // Handles two formats:
  //   Simple (ATS modules):    { filled: ['first_name', ...], skipped: [...] }
  //   Rich (universal module): { filled: [{ key, confidence, el, verify }], uncertain: [...] }

  function renderResults (rawResults, uploadResult) {
    const { filled = [], skipped = [], errors = [], uncertain = [] } = rawResults;

    // Normalise: if items are strings (ATS modules), wrap them
    const normFilled    = filled.map(f    => typeof f === 'string' ? { key: f, confidence: 100, verify: false } : f);
    const normSkipped   = skipped.map(s   => typeof s === 'string' ? { key: s } : s);
    const normErrors    = errors.map(e    => typeof e === 'string' ? { key: e } : e);

    const autoFilled    = normFilled.filter(f => !f.verify);
    const verifyFilled  = normFilled.filter(f =>  f.verify);

    let html = '<div class="rw-status-header">Results</div>';

    // ── Resume upload status (only shown if attempted) ─────────────────────
    if (uploadResult) {
      switch (uploadResult.status) {
        case 'uploaded':
          html += `
            <div class="rw-result-row rw-ok">
              <span class="rw-result-icon">📎</span>
              Resume attached (${uploadResult.filename})
            </div>`;
          break;
        case 'no_input':
          // Page has no resume file input — silent, this is normal on many pages
          break;
        case 'no_resume':
          html += `
            <div class="rw-result-row rw-skip">
              <span class="rw-result-icon">○</span>
              Resume file not stored — re-upload your resume in ResumeWing to enable auto-attach.
            </div>`;
          break;
        case 'unsupported':
          html += `
            <div class="rw-verify-row" style="grid-template-columns:auto 1fr;">
              ⚠ Please attach your resume manually — this site uses a custom uploader.
            </div>`;
          break;
        case 'fetch_failed':
          html += `
            <div class="rw-result-row rw-error">
              <span class="rw-result-icon">✗</span>
              Resume fetch failed: ${uploadResult.error || 'unknown'}
            </div>`;
          break;
      }
    }

    // ── Auto-filled rows ────────────────────────────────────────────────────
    if (autoFilled.length) {
      html += autoFilled.map(f => `
        <div class="rw-result-row rw-ok">
          <span class="rw-result-icon">✓</span>
          ${formatKey(f.key)}
          ${f.confidence < 100 ? `<span style="font-size:10px;opacity:.5">${f.confidence}%</span>` : ''}
          ${f.source === 'ai' ? '<span class="rw-ai-badge">✦ AI</span>' : ''}
        </div>`).join('');
    }

    // ── Needs verification rows (medium confidence — yellow) ────────────────
    if (verifyFilled.length) {
      html += `
        <div class="rw-verify-section">
          <div class="rw-verify-header">⚠ Please verify these fills</div>
          ${verifyFilled.map(f => `
            <div class="rw-verify-row">
              ⚠ ${formatKey(f.key)}
              <span style="font-size:10px;opacity:.6">${f.confidence}% confident</span>
            </div>`).join('')}
        </div>`;
    }

    // ── Unknown / unclassified fields — user labeler ─────────────────────
    if (uncertain.length) {
      const fieldOptions = [
        'first_name','last_name','email','phone','city','state','zip','country',
        'linkedin','github','portfolio','current_company','job_title',
        'years_experience','expected_salary','notice_period',
        'work_authorization','cover_letter','school','degree','major',
        'graduation_year','how_did_you_hear',
      ].map(k => `<option value="${k}">${formatKey(k)}</option>`).join('');

      html += `
        <div class="rw-unknown-section">
          <div class="rw-unknown-header">❓ Unrecognised fields — label to fill & remember</div>
          ${uncertain.map((u, i) => {
            const hint = u.signals?.label || u.signals?.placeholder || u.signals?.ariaLabel || `Field #${i+1}`;
            return `
              <div class="rw-unknown-row" data-idx="${i}">
                <span class="rw-unknown-label" title="${hint}">${hint.slice(0,28)}</span>
                <select class="rw-label-select" id="rw-sel-${i}">
                  <option value="">What is this?</option>
                  ${fieldOptions}
                </select>
                <button class="rw-label-apply-btn" data-idx="${i}">Fill</button>
              </div>`;
          }).join('')}
        </div>`;
    }

    // ── Errors ──────────────────────────────────────────────────────────────
    if (normErrors.length) {
      html += normErrors.map(e => `
        <div class="rw-result-row rw-error">
          <span class="rw-result-icon">✗</span>${formatKey(e.key || e)}
        </div>`).join('');
    }

    // ── Skipped ─────────────────────────────────────────────────────────────
    if (normSkipped.length) {
      html += normSkipped.map(s => `
        <div class="rw-result-row rw-skip">
          <span class="rw-result-icon">○</span>${formatKey(s.key || s)}
          <span style="font-size:10px;opacity:.5">(no value)</span>
        </div>`).join('');
    }

    // ── Summary ──────────────────────────────────────────────────────────────
    const totalFilled = normFilled.length;
    if (totalFilled > 0) {
      html += `<div class="rw-summary">
        <strong>${totalFilled} field${totalFilled === 1 ? '' : 's'} filled</strong>
        ${verifyFilled.length  ? ` · ${verifyFilled.length} need verification` : ''}
        ${uncertain.length     ? ` · ${uncertain.length} unrecognised` : ''}
        ${normErrors.length    ? ` · ${normErrors.length} error${normErrors.length > 1 ? 's':''}`  : ''}
      </div>`;
    } else {
      html += `<div class="rw-error-banner">
        No fields filled. This form may use unusual HTML.<br>
        Use the "What is this?" dropdowns above to label fields manually.
      </div>`;
    }

    statusEl.innerHTML = html;
    statusEl.classList.add('rw-visible');

    // ── Wire up the "Fill" buttons for unknown fields ─────────────────────
    statusEl.querySelectorAll('.rw-label-apply-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const idx      = parseInt(btn.dataset.idx, 10);
        const select   = document.getElementById(`rw-sel-${idx}`);
        const fieldKey = select?.value;
        if (!fieldKey || !profile) return;

        const field = uncertain[idx];
        if (!field?.el) return;

        const RW = window.ResumeWingATS;
        const ok = RW?.fillField?.(field.el, profile, fieldKey);
        if (ok) {
          // Persist the learned mapping
          RW?.learnMapping?.(location.hostname, field.selector, fieldKey);
          btn.textContent    = '✓';
          btn.style.color    = '#4ade80';
          btn.disabled       = true;
          select.disabled    = true;
        } else {
          btn.textContent    = '✗';
          btn.style.color    = '#f87171';
        }
      });
    });

    // ── Listen for AI results arriving asynchronously ─────────────────────
    // Preserve the upload status across re-renders by capturing it in closure.
    window.addEventListener('rw-ai-results-updated', (e) => {
      renderResults(e.detail, uploadResult);
    }, { once: true });
  }

  function formatKey (key) {
    return (key || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }

  // ── Kick off profile load ─────────────────────────────────────────────────
  loadProfile();

})();
