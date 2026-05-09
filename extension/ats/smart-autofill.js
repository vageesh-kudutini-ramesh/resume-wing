/**
 * ResumeWing — Smart Autofill for application questions
 *
 * Runs after the platform-specific module finishes filling its known fields.
 * Looks at what's STILL unfilled and asks the backend to draft answers:
 *
 *   • <textarea> / <input> with question-like labels  → POST /profile/answer-question
 *   • Radio button groups (Yes/No, multiple-choice)   → POST /profile/answer-question
 *                                                       (categorical fast-path
 *                                                        handles work auth /
 *                                                        sponsorship / start
 *                                                        date with no LLM call)
 *
 * Why this lives in its own file instead of inside universal.js:
 *   universal.js exits early when a platform module (Lever, Greenhouse,
 *   Workday, Ashby, SmartRecruiters) is registered, so its smart-autofill
 *   pass never ran for the most common ATS sites. This file is loaded by
 *   every content_scripts entry in manifest.json so RW.smartAutofill is
 *   always available, regardless of which platform module is active.
 *
 * All filled answers are marked "verify" (yellow) — the user MUST review
 * them before submitting the form.
 */

(function () {
  'use strict';

  if (!window.ResumeWingATS) {
    console.warn('[ResumeWing] smart-autofill.js: ResumeWingATS missing — common.js failed?');
    return;
  }
  const RW = window.ResumeWingATS;

  const BACKEND_URL = 'http://localhost:8000/profile/answer-question';

  // ── Question detection ─────────────────────────────────────────────────────

  const QUESTION_WORDS = [
    'why ', 'how ', 'what ', 'when ', 'where ', 'do you ', 'are you ', 'have you ',
    'tell us', 'describe', 'explain', 'share ', 'in your own words',
    'cover letter', 'motivation', 'interested in', 'what makes you',
    'why this role', 'why our', 'authoriz', 'sponsor', 'visa',
    'notice period', 'salary', 'compensation', 'relocate', 'start date',
    'eligible', 'legally', 'available',
  ];

  // Demographic / EEOC fields. These are voluntary self-identification
  // questions on US job applications — auto-filling them would be wrong:
  // the user must consent and choose themselves. Always skip.
  const SENSITIVE_PATTERNS = [
    /\bgender\b/i, /\bsex\b/i, /\bpronouns?\b/i,
    /\brace\b/i, /\bethnic(ity)?\b/i, /\bhispanic\b/i, /\blatin\b/i,
    /\bveteran\b/i, /\bmilitary\s+status\b/i,
    /\bdisabilit(y|ies)\b/i, /\bdisabled\b/i,
    /\bdemograph/i, /\bvoluntary\s+(self|disclosure)/i,
    /\beeoc?\b/i, /\bequal\s+(employment|opportunity)/i,
    /\bage\s+range\b/i, /\bdate\s+of\s+birth\b/i, /\bdob\b/i,
  ];

  function _isSensitiveField (labelText) {
    if (!labelText) return false;
    return SENSITIVE_PATTERNS.some(rx => rx.test(labelText));
  }

  function _looksLikeQuestion (labelText) {
    if (!labelText) return false;
    const t = labelText.toLowerCase();
    if (t.includes('?')) return true;
    return QUESTION_WORDS.some(w => t.includes(w));
  }

  // ── Find the question text for a given input ──────────────────────────────

  function _isVisible (el) {
    if (!el || el.offsetWidth === 0 && el.offsetHeight === 0) return false;
    const s = window.getComputedStyle(el);
    return s.display !== 'none' && s.visibility !== 'hidden' && parseFloat(s.opacity) > 0;
  }

  function _questionForInput (el) {
    // 1. <label for="X">
    if (el.id) {
      const lbl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lbl) {
        const t = (lbl.textContent || '').trim();
        if (t) return t;
      }
    }
    // 2. Wrapping label
    const wrap = el.closest('label');
    if (wrap) {
      const t = (wrap.textContent || '').trim();
      if (t) return t;
    }
    // 3. aria-label / aria-labelledby
    const aria = el.getAttribute('aria-label');
    if (aria && aria.trim()) return aria.trim();
    const labelledBy = el.getAttribute('aria-labelledby');
    if (labelledBy) {
      const target = document.getElementById(labelledBy);
      if (target) return (target.textContent || '').trim();
    }
    // 4. Walk up to find a <legend>, label, or heading sibling
    let node = el.parentElement;
    for (let depth = 0; depth < 5 && node; depth++) {
      const candidates = node.querySelectorAll(
        'legend, label, h3, h4, p[class*="label" i], div[class*="label" i], div[class*="question" i]'
      );
      for (const c of candidates) {
        if (c.contains(el)) continue;  // Same container, skip
        const t = (c.textContent || '').trim();
        if (t && t.length < 250) return t;
      }
      node = node.parentElement;
    }
    // 5. Placeholder as last resort
    return el.placeholder || '';
  }

  function _questionForRadioGroup (radios) {
    // Use the first radio as the anchor; walk up to find legend or heading
    const first = radios[0];
    // 1. Fieldset → legend
    const fs = first.closest('fieldset');
    if (fs) {
      const legend = fs.querySelector(':scope > legend, legend');
      if (legend) {
        const t = (legend.textContent || '').trim();
        if (t) return t;
      }
    }
    // 2. Walk up
    let node = first.parentElement;
    for (let depth = 0; depth < 5 && node; depth++) {
      // Skip the immediate radio container — go for the labelled wrapper
      const candidates = node.querySelectorAll(
        'legend, h3, h4, label[class*="question" i], div[class*="question" i], div[class*="label" i], p[class*="label" i]'
      );
      for (const c of candidates) {
        // Skip labels for the radios themselves (they say "Yes" / "No")
        const t = (c.textContent || '').trim();
        if (!t || t.length > 300) continue;
        if (radios.some(r => c.contains(r))) continue;
        if (t.toLowerCase() === 'yes' || t.toLowerCase() === 'no') continue;
        return t;
      }
      node = node.parentElement;
    }
    return '';
  }

  // ── Profile-field patterns ─────────────────────────────────────────────────
  //
  // When the platform module (Greenhouse, Lever, Workday, Ashby, ...) doesn't
  // know about a custom application question — but that question is actually
  // a standard profile field with a different label — we can still fill it
  // by matching the label text. Each entry is { regex, getValue }; getValue
  // receives the profile and returns the string value (or empty string).
  //
  // Runs BEFORE the LLM question-answer pass so we don't waste an Ollama
  // call on a field we can answer from structured profile data instantly.

  function _firstNonEmpty (...values) {
    for (const v of values) if (v && String(v).trim()) return String(v).trim();
    return '';
  }

  const PROFILE_FIELD_PATTERNS = [
    // Location
    { rx: /\b(country\s+of\s+residence|country\s+of\s+citizenship|country)\b/i,
      getValue: p => p.personal?.country || 'United States' },
    { rx: /\b(state\s+of\s+residence|state\s*\/?\s*province|state|province|region)\b/i,
      getValue: p => _firstNonEmpty(p.personal?.state_full, p.personal?.state) },
    { rx: /\b(city\s+of\s+residence|current\s+city|city|town|municipality)\b/i,
      getValue: p => p.personal?.city || '' },
    { rx: /\b(zip|postal|post[\s_-]?code|postcode|pincode)\b/i,
      getValue: p => p.personal?.zip || '' },
    { rx: /\b(street\s*address|address[\s_-]?line|mailing\s*address)\b/i,
      getValue: _ => '' /* never auto-fill street; not in resume reliably */ },

    // Education
    { rx: /\b(school|university|college|institution|alma\s+mater)\b/i,
      getValue: p => p.education?.[0]?.school || '' },
    { rx: /\b(degree|highest\s+degree|level\s+of\s+education|qualification)\b/i,
      getValue: p => p.education?.[0]?.degree || '' },
    { rx: /\b(major|field\s+of\s+study|concentration|discipline|area\s+of\s+study)\b/i,
      getValue: p => p.education?.[0]?.major || '' },
    { rx: /\b(graduation\s+year|year\s+of\s+graduation|grad\s+year|pass\s*out\s+year)\b/i,
      getValue: p => p.education?.[0]?.graduation_year || '' },
    { rx: /\bgpa\b/i,
      getValue: p => p.education?.[0]?.gpa || '' },

    // Work
    { rx: /\b(current\s+company|current\s+employer|present\s+employer|company\s+name|employer)\b/i,
      getValue: p => p.work_experience?.[0]?.company || '' },
    { rx: /\b(current\s+(title|role|position)|job\s+title|present\s+title|designation)\b/i,
      getValue: p => p.work_experience?.[0]?.title || '' },
    { rx: /\b(years\s+of\s+(experience|exp)|total\s+experience|how\s+many\s+years)\b/i,
      getValue: p => String(p.metadata?.years_experience || '') },

    // Links
    { rx: /\blinkedin\b/i, getValue: p => p.links?.linkedin || '' },
    { rx: /\bgithub\b/i,   getValue: p => p.links?.github || '' },
    { rx: /\b(portfolio|personal\s+(site|website)|website)\b/i,
      getValue: p => p.links?.portfolio || '' },
  ];


  // ── Backend call ───────────────────────────────────────────────────────────

  async function _askBackend (question, fieldType, maxLen) {
    try {
      const res = await fetch(BACKEND_URL, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question,
          field_type: fieldType,
          jd_context: document.title || '',
          max_length: maxLen || null,
        }),
      });
      if (!res.ok) return null;
      return await res.json();   // { answer, confidence, source }
    } catch (_) {
      return null;
    }
  }

  // ── Main: scan + fill ──────────────────────────────────────────────────────

  /**
   * Scan the page for unfilled question fields and have the backend draft
   * answers. Mutates `results` in place — appends filled fields as
   * verify-yellow rows so the user reviews before submitting.
   */
  RW.smartAutofill = async function (profile, results) {
    if (!results) results = { filled: [], skipped: [], errors: [] };
    if (!profile) return results;

    // ── 0. Profile-field pass ────────────────────────────────────────────────
    // Match unfilled inputs/selects/textareas against known profile-field
    // labels (Country, State, City, School, Degree, Major, GPA, etc.) and
    // fill from the structured profile. Runs first so the LLM question-answer
    // pass doesn't waste a call on these.
    const allCandidates = Array.from(document.querySelectorAll(
      'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="reset"]):not([type="image"]):not([type="file"]):not([type="checkbox"]):not([type="radio"]):not([readonly]),'
      + 'textarea:not([readonly]), select'
    )).filter(el => {
      if (!_isVisible(el)) return false;
      // Already filled?
      if (el.tagName === 'SELECT') {
        if (el.selectedIndex > 0 && el.options[el.selectedIndex]?.value?.trim()) return false;
      } else {
        if ((el.value || '').trim()) return false;
      }
      return true;
    });

    for (const el of allCandidates) {
      const labelText = _questionForInput(el);
      if (!labelText) continue;
      // Skip sensitive fields — never auto-fill demographics
      if (_isSensitiveField(labelText)) continue;

      // Match against profile-field patterns
      let matchedValue = '';
      for (const { rx, getValue } of PROFILE_FIELD_PATTERNS) {
        if (rx.test(labelText)) {
          try { matchedValue = getValue(profile) || ''; } catch { matchedValue = ''; }
          if (matchedValue) break;
        }
      }
      if (!matchedValue) continue;

      // Fill: select uses fillSelect, others use fillInput (which now also
      // delegates selects internally — this branch is just a safety net).
      let ok = false;
      if (el.tagName === 'SELECT') {
        ok = !!RW.fillSelect(el, matchedValue);
      } else {
        ok = !!RW.fillInput(el, matchedValue);
      }
      if (!ok) continue;

      RW.highlight(el);
      results.filled.push({
        key:        `Profile: ${labelText.slice(0, 40)}…`,
        confidence: 95,
        verify:     false,
        source:     'profile',
      });
    }

    // ── 1. Text inputs and textareas ─────────────────────────────────────────
    const textCandidates = Array.from(document.querySelectorAll(
      'textarea, input[type="text"]:not([readonly]), input[type="email"]:not([readonly]), input:not([type]):not([readonly])'
    )).filter(el => {
      if (!_isVisible(el)) return false;
      if ((el.value || '').trim()) return false;   // Already filled
      // Don't touch fields the platform module just filled
      if (el.dataset.rwFilled) return false;
      return true;
    });

    for (const el of textCandidates) {
      const question = _questionForInput(el);
      if (!_looksLikeQuestion(question)) continue;
      if (question.length < 6) continue;
      if (_isSensitiveField(question)) continue;  // Skip EEOC / demographic

      const fieldType = el.tagName === 'TEXTAREA' ? 'textarea' : 'input';
      const maxLen    = parseInt(el.getAttribute('maxlength') || '0', 10) || null;

      const ans = await _askBackend(question, fieldType, maxLen);
      if (!ans || !ans.answer) continue;

      const ok = RW.fillInput(el, ans.answer);
      if (!ok) continue;

      _highlightVerify(el);
      results.filled.push({
        key:        `Q: ${question.slice(0, 40)}…`,
        confidence: Math.round((ans.confidence || 0.7) * 100),
        verify:     true,
        source:     ans.source === 'profile' ? 'profile' : 'ai',
      });
    }

    // ── 2. Select dropdowns ──────────────────────────────────────────────────
    // Selects whose options aren't a literal "Yes"/"No"/profile-value match
    // (the platform module's fillSelect couldn't pair them up) end up
    // unfilled. Treat them like radios: ask the backend, then find the
    // option whose label matches the answer.
    const selectCandidates = Array.from(document.querySelectorAll('select')).filter(el => {
      if (!_isVisible(el)) return false;
      // Already-chosen selects: a real option has been picked (selectedIndex
      // > 0 and that option has a non-empty value)
      if (el.selectedIndex > 0) {
        const v = el.options[el.selectedIndex]?.value;
        if (v && v.trim()) return false;
      }
      // Skip if there's only a placeholder option
      if (el.options.length <= 1) return false;
      return true;
    });

    for (const el of selectCandidates) {
      const question = _questionForInput(el);
      if (!question || question.length < 4) continue;
      if (_isSensitiveField(question)) continue;  // Skip EEOC / demographic

      const ans = await _askBackend(question, 'select', null);
      if (!ans || !ans.answer) continue;

      const target = ans.answer.trim().toLowerCase();
      let chosen = null;

      for (const opt of el.options) {
        // Skip placeholder options — they have empty value
        if (!opt.value || !opt.value.trim()) continue;
        const t = (opt.text || '').trim().toLowerCase();
        if (!t) continue;
        if (t === target ||
            t.startsWith(target) ||
            target.startsWith(t) ||
            (target.length > 3 && t.includes(target)) ||
            (opt.value || '').toLowerCase() === target) {
          chosen = opt;
          break;
        }
      }
      // Yes/No fallback for boolean answers
      if (!chosen) {
        for (const opt of el.options) {
          if (!opt.value || !opt.value.trim()) continue;
          const t = (opt.text || '').trim().toLowerCase();
          if (target.startsWith('y') && t.startsWith('y')) { chosen = opt; break; }
          if (target.startsWith('n') && t.startsWith('n')) { chosen = opt; break; }
        }
      }
      if (!chosen) continue;

      try {
        el.value = chosen.value;
        el.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
        _highlightVerify(el);
        results.filled.push({
          key:        `Q: ${question.slice(0, 40)}…`,
          confidence: Math.round((ans.confidence || 0.8) * 100),
          verify:     true,
          source:     ans.source === 'profile' ? 'profile' : 'ai',
        });
      } catch (_) { /* select rejected — skip */ }
    }

    // ── 3. Radio groups ──────────────────────────────────────────────────────
    const allRadios = Array.from(document.querySelectorAll('input[type="radio"]'));
    const groups = new Map();   // name → [radios]
    for (const r of allRadios) {
      if (!_isVisible(r)) continue;
      const name = r.name || `__no_name_${groups.size}`;
      if (!groups.has(name)) groups.set(name, []);
      groups.get(name).push(r);
    }

    for (const [name, radios] of groups) {
      // Skip if any radio is already selected (user/platform pre-filled)
      if (radios.some(r => r.checked)) continue;

      const question = _questionForRadioGroup(radios);
      if (!question || question.length < 6) continue;
      if (_isSensitiveField(question)) continue;  // Skip EEOC / demographic

      const ans = await _askBackend(question, 'radio', null);
      if (!ans || !ans.answer) continue;

      const target = ans.answer.trim().toLowerCase();
      // Find the radio whose label/value best matches the answer
      let chosen = null;
      for (const r of radios) {
        const lbl = r.id ? document.querySelector(`label[for="${CSS.escape(r.id)}"]`) : null;
        const labelText = (lbl?.textContent || r.value || '').trim().toLowerCase();
        if (labelText === target ||
            labelText.startsWith(target) ||
            target.startsWith(labelText) ||
            (r.value || '').toLowerCase() === target) {
          chosen = r; break;
        }
      }
      // Fallback: if backend said "Yes" / "No", match the first radio that
      // has a label starting with that word
      if (!chosen) {
        for (const r of radios) {
          const lbl = r.id ? document.querySelector(`label[for="${CSS.escape(r.id)}"]`) : null;
          const t = (lbl?.textContent || '').trim().toLowerCase();
          if (target.startsWith('y') && t.startsWith('y')) { chosen = r; break; }
          if (target.startsWith('n') && t.startsWith('n')) { chosen = r; break; }
        }
      }

      if (!chosen) continue;
      try {
        chosen.click();
        _highlightVerify(chosen);
        results.filled.push({
          key:        `Q: ${question.slice(0, 40)}…`,
          confidence: Math.round((ans.confidence || 0.9) * 100),
          verify:     true,
          source:     ans.source === 'profile' ? 'profile' : 'ai',
        });
      } catch (_) { /* radio click rejected — skip */ }
    }

    return results;
  };

  // ── Helpers ────────────────────────────────────────────────────────────────

  function _highlightVerify (el) {
    if (!el) return;
    const target = (el.type === 'radio') ? (el.closest('label') || el) : el;
    const prev = target.style.outline;
    target.style.outline = '2px solid #facc15';
    target.style.transition = 'outline 0.3s';
    setTimeout(() => { target.style.outline = prev; }, 4000);
  }

})();
