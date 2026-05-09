/**
 * ResumeWing Autofill — Lever ATS Module
 *
 * Covers jobs.lever.co/<company>/<job-id>/apply application forms.
 *
 * Lever uses a clean, standardised form with `name` attributes that are
 * very stable across all companies on the platform.
 * Social links use the pattern `urls[LinkedIn]`, `urls[GitHub]`, etc.
 *
 * Lever renders a single-page form (no multi-step) so no page navigation needed.
 */

(function () {
  'use strict';

  const RW = window.ResumeWingATS;

  // ── Default field selectors ───────────────────────────────────────────────

  const DEFAULTS = {
    // Lever combines first+last into one "name" field on most applications.
    // Some job postings split it; we handle both cases.
    full_name: [
      'input[name="name"]',
      '.application-name input',
      'input[autocomplete="name"]',
      'input[placeholder*="Full name" i]',
      'input[placeholder*="Your name" i]',
    ],
    first_name: [
      'input[name="first_name"]',
      'input[placeholder*="First name" i]',
      'input[autocomplete="given-name"]',
    ],
    last_name: [
      'input[name="last_name"]',
      'input[placeholder*="Last name" i]',
      'input[autocomplete="family-name"]',
    ],
    email: [
      'input[name="email"]',
      'input[type="email"]',
    ],
    phone: [
      'input[name="phone"]',
      'input[type="tel"]',
      'input[placeholder*="Phone" i]',
    ],
    current_company: [
      'input[name="org"]',
      'input[placeholder*="Current company" i]',
      'input[placeholder*="Company" i]',
    ],
    linkedin: [
      'input[name="urls[LinkedIn]"]',
      'input[placeholder*="LinkedIn" i]',
      'input[id*="linkedin" i]',
    ],
    github: [
      'input[name="urls[GitHub]"]',
      'input[placeholder*="GitHub" i]',
      'input[id*="github" i]',
    ],
    portfolio: [
      'input[name="urls[Portfolio]"]',
      'input[name="urls[Other]"]',
      'input[placeholder*="Portfolio" i]',
      'input[placeholder*="Website" i]',
    ],
    location: [
      'input[name="location"]',
      'input[placeholder*="Location" i]',
      'input[placeholder*="City" i]',
    ],
    summary: [
      'textarea[name="comments"]',
      'textarea[placeholder*="cover letter" i]',
      'textarea[placeholder*="anything else" i]',
    ],
  };

  // ── Main fill function ────────────────────────────────────────────────────

  async function fill (profile, customSelectors = {}) {
    const sel = {};
    for (const key of Object.keys(DEFAULTS)) {
      sel[key] = [...(customSelectors[key] ?? []), ...DEFAULTS[key]];
    }

    const results = { filled: [], skipped: [], errors: [] };
    const p = profile.personal;
    const l = profile.links;
    const w = profile.work_experience?.[0] ?? {};

    // ── Try full name first; if that field doesn't exist, split first/last ──
    const fullNameSel = RW.fillBySelectorList(
      sel.full_name,
      [p.first_name, p.last_name].filter(Boolean).join(' ')
    );

    if (fullNameSel) {
      results.filled.push('full_name');
      RW.highlight(document.querySelector(fullNameSel));
    } else {
      // Split name fields
      for (const { key, value } of [
        { key: 'first_name', value: p.first_name },
        { key: 'last_name',  value: p.last_name  },
      ]) {
        if (!value) { results.skipped.push(key); continue; }
        const matched = RW.fillBySelectorList(sel[key], value);
        matched
          ? (results.filled.push(key), RW.highlight(document.querySelector(matched)))
          : results.skipped.push(key);
      }
    }

    // ── Remaining standard fields ──────────────────────────────────────────
    // labelRegex is the fallback when the CSS selector list misses — many
    // Lever-hosted custom application forms use generic input names (e.g.
    // urls[1] instead of urls[LinkedIn]) so we match by visible label text
    // as a second attempt.
    const standardFields = [
      { key: 'email',           value: p.email,                                      labelRegex: /\bemail\b/i },
      { key: 'phone',           value: p.phone,                                      labelRegex: /\b(phone|mobile|tel)\b/i },
      { key: 'current_company', value: w.company,                                    labelRegex: /\b(current\s+company|employer|company)\b/i },
      { key: 'location',        value: [p.city, p.state].filter(Boolean).join(', '), labelRegex: /\b(location|current\s+location|city)\b/i },
      { key: 'linkedin',        value: l.linkedin,                                   labelRegex: /\blinkedin\b/i },
      { key: 'github',          value: l.github,                                     labelRegex: /\bgithub\b/i },
      { key: 'portfolio',       value: l.portfolio,                                  labelRegex: /\b(portfolio|website|personal\s+site|other\s+website)\b/i },
    ];

    for (const { key, value, labelRegex } of standardFields) {
      if (!value) { results.skipped.push(key); continue; }
      try {
        // 1. CSS selector list (fast path for sites using stable Lever names)
        const matched = RW.fillBySelectorList(sel[key] ?? [], value);
        if (matched) {
          results.filled.push(key);
          RW.highlight(document.querySelector(matched));
          continue;
        }

        // 2. Label-text fallback — for custom-named inputs
        const labelEl = labelRegex ? RW.fillByLabel(labelRegex, value) : null;
        if (labelEl) {
          results.filled.push(key);
          RW.highlight(labelEl);
          continue;
        }

        results.skipped.push(key);
      } catch (_) {
        results.errors.push(key);
      }
    }

    return results;
  }

  // ── ATS detection ─────────────────────────────────────────────────────────

  function detect () {
    return location.hostname.includes('lever.co');
  }

  // ── Register module ───────────────────────────────────────────────────────
  RW.module = { name: 'Lever', fill, detect };

})();
