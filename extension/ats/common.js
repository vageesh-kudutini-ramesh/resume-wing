/**
 * ResumeWing Autofill — Shared ATS Utilities
 *
 * Loaded before every ATS-specific module. Sets up the `window.ResumeWingATS`
 * namespace with primitives that work across React, Vue, Angular, react-hook-form,
 * Formik, and plain HTML forms.
 *
 * Why no ES modules?
 * ──────────────────
 * Chrome content scripts don't support top-level `import`. Scripts share the
 * page's window object, so we use a global namespace pattern instead.
 *
 * Each ATS-specific script (greenhouse.js, lever.js, …) registers itself by
 * setting `window.ResumeWingATS.module = { name, fill, detect }`.
 * content.js then reads `window.ResumeWingATS.module` to know which filler to call.
 */

(function () {
  'use strict';

  console.log('[ResumeWing] common.js injected on:', location.href);

  // Guard: only initialise once per page (content_scripts entries can overlap)
  if (window.ResumeWingATS) return;

  const RW = (window.ResumeWingATS = {});

  // ── Field-fill primitives ─────────────────────────────────────────────────

  /**
   * Set the value of an <input> or <textarea> using the native prototype
   * setter, then dispatch the standard input + change events.
   *
   * Why this works for React, Vue, Angular, react-hook-form, Formik:
   *   When you set `el.value = x` directly on a React-controlled input,
   *   React intercepts it and ignores your write because its own state is
   *   the source of truth. But when you use the *prototype's* native setter
   *   (which React's wrapper preserves) and then fire an `input` event,
   *   React's synthetic event handler picks it up and updates state correctly.
   *
   * This is the same trick Cypress and Playwright use under the hood.
   * It replaces the fragile fiber-tree-walking we used to do.
   */
  RW.fillInput = function (el, value) {
    if (!el || value === undefined || value === null || value === '') return false;

    // Selects need OPTION-text matching, not raw value-setting. Setting
    // `select.value = "Yes"` silently no-ops if no <option> has value="Yes",
    // which produced misleading "filled" reports in the panel. Route to
    // fillSelect — it returns false honestly when no option matches.
    if (el.tagName === 'SELECT') {
      return RW.fillSelect(el, value);
    }

    try {
      const proto = Object.getPrototypeOf(el);
      const desc  = Object.getOwnPropertyDescriptor(proto, 'value')
                 || Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')
                 || Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value');

      if (desc && desc.set) {
        desc.set.call(el, String(value));
      } else {
        el.value = String(value);
      }

      // Some frameworks (Angular Forms) need focus + blur to mark the field as touched
      el.dispatchEvent(new Event('input',  { bubbles: true, cancelable: true }));
      el.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
      el.dispatchEvent(new Event('blur',   { bubbles: true, cancelable: true }));
      return true;
    } catch (err) {
      console.warn('[ResumeWing] fillInput failed:', err);
      return false;
    }
  };

  /**
   * Backward-compat alias. The old fiber-walking implementation broke on
   * react-hook-form, Formik, and Workday's shadow DOM. The native-setter
   * approach in fillInput works for all of them, so this is just an alias now.
   */
  RW.fillReactInput = function (el, value) {
    return RW.fillInput(el, value);
  };

  /**
   * Fill a <select> by value or display text (exact then prefix match).
   * Returns true on success, false if no option matched.
   */
  RW.fillSelect = function (el, value) {
    if (!el || !value) return false;
    const lower = String(value).toLowerCase();

    for (const opt of el.options) {
      if (opt.value === value || opt.text.trim() === value) {
        el.value = opt.value;
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
      }
    }

    for (const opt of el.options) {
      if (opt.text.toLowerCase().startsWith(lower) ||
          opt.value.toLowerCase() === lower ||
          opt.text.toLowerCase().includes(lower)) {
        el.value = opt.value;
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
      }
    }

    return false;
  };

  /**
   * Try each CSS selector in order; fill the first matching element.
   * Returns the winning selector string, or null.
   */
  RW.fillBySelectorList = function (selectorList, value) {
    if (!value || !selectorList?.length) return null;

    for (const selector of selectorList) {
      try {
        const el = document.querySelector(selector);
        if (!el) continue;

        const tag  = el.tagName.toLowerCase();
        const type = el.type?.toLowerCase();

        let ok = false;
        if (tag === 'select') {
          ok = RW.fillSelect(el, value);
        } else if (type === 'checkbox' || type === 'radio') {
          continue;
        } else {
          ok = RW.fillInput(el, value);
        }

        if (ok) return selector;
      } catch (_) {
        // Bad selector — skip silently
      }
    }

    return null;
  };

  /**
   * Click a radio or checkbox whose label text or value matches `value`.
   */
  RW.fillRadio = function (groupNameOrSelector, value) {
    let radios;
    try {
      radios = document.querySelectorAll(
        `[name="${groupNameOrSelector}"], ${groupNameOrSelector}`
      );
    } catch (_) {
      radios = document.querySelectorAll(`[name="${groupNameOrSelector}"]`);
    }
    const lower = String(value).toLowerCase();

    for (const r of radios) {
      const labelText = r.labels?.[0]?.textContent?.trim().toLowerCase() || '';
      if (r.value.toLowerCase() === lower || labelText === lower || labelText.includes(lower)) {
        r.click();
        return true;
      }
    }
    return false;
  };

  // ── Label-based field finder (fallback when CSS selectors miss) ───────────

  /**
   * Find the most likely input/textarea/select for a field whose visible
   * label matches `labelRegex`. Used by platform modules as a fallback when
   * their CSS selector list misses (e.g. when a Lever-hosted form uses
   * generic input names like `urls[1]` instead of `urls[LinkedIn]`).
   *
   * Lookup order:
   *   1. <label for="X"> with matching text → element with id X
   *   2. <label>...<input>...</label> (wrapped) with matching text
   *   3. Inputs near a sibling label/heading whose text matches
   *
   * Returns the element (so the caller can highlight it), or null.
   */
  RW.findInputByLabel = function (labelRegex) {
    if (!(labelRegex instanceof RegExp)) labelRegex = new RegExp(labelRegex, 'i');

    // Pass 1: explicit <label for="X"> → element by id
    for (const label of document.querySelectorAll('label')) {
      const text = (label.textContent || '').trim();
      if (!text || !labelRegex.test(text)) continue;
      const forId = label.getAttribute('for');
      if (forId) {
        const el = document.getElementById(forId);
        if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT')) {
          return el;
        }
      }
      // Pass 2: wrapped <label>X<input/></label>
      const wrapped = label.querySelector('input, textarea, select');
      if (wrapped) return wrapped;
    }

    // Pass 3: walk up from each input looking for a sibling/ancestor label
    const inputs = document.querySelectorAll('input, textarea, select');
    for (const el of inputs) {
      if (!el.matches('input, textarea, select')) continue;
      // Skip hidden / submit / file (file is handled separately)
      const t = (el.type || '').toLowerCase();
      if (['hidden', 'submit', 'button', 'reset', 'image', 'file'].includes(t)) continue;

      let node = el.parentElement;
      for (let depth = 0; depth < 4 && node; depth++) {
        // Look for a sibling/ancestor that isn't the input itself
        const candidates = node.querySelectorAll(
          'label, legend, [class*="label" i], [class*="Label" i]'
        );
        for (const c of candidates) {
          const t = (c.textContent || '').trim();
          // Reject very long candidates — likely paragraph text, not a label
          if (t && t.length < 120 && labelRegex.test(t)) {
            return el;
          }
        }
        node = node.parentElement;
      }
    }
    return null;
  };

  /**
   * Convenience: find by label and fill in one call.
   * Returns the element on success (so caller can highlight), null on failure.
   */
  RW.fillByLabel = function (labelRegex, value) {
    if (!value) return null;
    const el = RW.findInputByLabel(labelRegex);
    if (!el) return null;
    if (el.tagName === 'SELECT') {
      return RW.fillSelect(el, value) ? el : null;
    }
    return RW.fillInput(el, value) ? el : null;
  };

  // ── File upload via DataTransfer API ──────────────────────────────────────

  /**
   * Programmatically attach a file (the user's resume) to an `<input type="file">`.
   *
   * Background:
   *   For security, browsers don't let you set `input.value` for file inputs.
   *   But you CAN assign a `FileList` to `input.files` if the FileList comes
   *   from a DataTransfer object — which is exactly the same mechanism
   *   drag-and-drop uses internally. This works in Chromium-based browsers
   *   (Edge, Chrome) including from extension content scripts.
   *
   * What can fail:
   *   - Sites that use a custom file picker without a real `<input type="file">`
   *     (we'd need a non-standard hack per site, which we don't do).
   *   - Sites that listen for a 'click' on the picker button rather than the
   *     `change` event on the input.
   *   - Strict CSP on a few sites blocking Blob URL creation.
   *
   * On any failure the caller falls back to telling the user "please upload
   * the resume manually" while continuing to fill all the text fields.
   *
   * @param {HTMLInputElement} input    - The file input element to populate
   * @param {ArrayBuffer}      bytes    - File bytes (from /resume/file backend)
   * @param {string}           filename - e.g. "JohnDoe_Resume.pdf"
   * @param {string}           mimeType - e.g. "application/pdf"
   * @returns {boolean} true if the file was attached and a change event fired
   */
  RW.fillFile = function (input, bytes, filename, mimeType) {
    if (!input || input.tagName !== 'INPUT' || input.type !== 'file') return false;
    if (!bytes || !filename) return false;

    try {
      const blob = new Blob([bytes], { type: mimeType || 'application/octet-stream' });
      const file = new File([blob], filename, {
        type:         mimeType || 'application/octet-stream',
        lastModified: Date.now(),
      });

      const dt = new DataTransfer();
      dt.items.add(file);
      input.files = dt.files;

      input.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
      input.dispatchEvent(new Event('input',  { bubbles: true, cancelable: true }));
      return true;
    } catch (err) {
      console.warn('[ResumeWing] fillFile failed:', err);
      return false;
    }
  };

  /**
   * Find the most likely resume-upload file input on the current page.
   *
   * Heuristics (in order of specificity):
   *   1. file input with name/id/aria-label containing 'resume', 'cv', 'attach'
   *   2. file input that accepts pdf/doc — and isn't for cover letter / portfolio
   *   3. first visible file input on the page
   *
   * Returns the element, or null.
   */
  RW.findResumeFileInput = function () {
    const inputs = Array.from(document.querySelectorAll('input[type="file"]'));
    if (!inputs.length) return null;

    const visible = inputs.filter(el => {
      const r = el.getBoundingClientRect();
      const s = window.getComputedStyle(el);
      // File inputs are often visually hidden but functionally present —
      // hide check is loose: only skip display:none + visibility:hidden
      return s.display !== 'none' && s.visibility !== 'hidden';
    });

    const hasResumeSignal = el => {
      const s = `${el.name || ''} ${el.id || ''} ${el.getAttribute('aria-label') || ''} ${el.getAttribute('data-testid') || ''}`.toLowerCase();
      return /(resume|^cv$|\bcv\b|attach|upload)/.test(s);
    };
    const isOtherDoc = el => {
      const s = `${el.name || ''} ${el.id || ''} ${el.getAttribute('aria-label') || ''}`.toLowerCase();
      return /(cover[\s_-]?letter|portfolio|transcript|reference|writing[\s_-]?sample)/.test(s);
    };

    // 1. Resume-signal match, not a cover letter
    let best = visible.find(el => hasResumeSignal(el) && !isOtherDoc(el));
    if (best) return best;

    // 2. Accepts PDF or DOC and isn't a cover letter
    best = visible.find(el => {
      const accept = (el.accept || '').toLowerCase();
      return /(pdf|doc|application\/pdf)/.test(accept) && !isOtherDoc(el);
    });
    if (best) return best;

    // 3. Any non-cover-letter file input
    best = visible.find(el => !isOtherDoc(el));
    return best || visible[0] || inputs[0];
  };

  // ── DOM helpers ───────────────────────────────────────────────────────────

  /**
   * Wait for a CSS selector to appear (for lazy-rendered SPA pages).
   * Returns a Promise that resolves to the element, or rejects after `timeoutMs`.
   */
  RW.waitForElement = function (selector, timeoutMs = 8000) {
    return new Promise((resolve, reject) => {
      const el = document.querySelector(selector);
      if (el) return resolve(el);

      const obs = new MutationObserver(() => {
        const found = document.querySelector(selector);
        if (found) {
          obs.disconnect();
          resolve(found);
        }
      });

      obs.observe(document.documentElement, { childList: true, subtree: true });

      setTimeout(() => {
        obs.disconnect();
        reject(new Error(`Timeout: element "${selector}" not found after ${timeoutMs}ms`));
      }, timeoutMs);
    });
  };

  /**
   * Brief green-outline flash on a successfully-filled field.
   */
  RW.highlight = function (el) {
    if (!el) return;
    const prev      = el.style.outline;
    const prevTrans = el.style.transition;
    el.style.outline    = '2px solid #22c55e';
    el.style.transition = 'outline 0.3s ease';
    setTimeout(() => {
      el.style.outline    = prev;
      el.style.transition = prevTrans;
    }, 1800);
  };

  RW.highlightAll = function (selectorList) {
    (selectorList || []).forEach(sel => {
      try { RW.highlight(document.querySelector(sel)); } catch (_) {}
    });
  };

  RW.sleep = ms => new Promise(r => setTimeout(r, ms));

  // ── ATS module registry ───────────────────────────────────────────────────
  // Each ats/platform.js sets this to { name, fill, detect }
  RW.module = null;

})();
