/**
 * ResumeWing Autofill — Ashby ATS Module
 *
 * Covers app.ashbyhq.com and jobs.ashbyhq.com application forms.
 *
 * Ashby uses a clean React-based form. Key characteristics:
 * - `data-testid` attributes for core personal fields.
 * - Social/portfolio links as plain text inputs.
 * - Custom questions rendered as labelled inputs — handled by label-matching.
 * - Single-page form (no multi-step navigation).
 *
 * Ashby is startup-focused; companies often add custom questions that vary
 * widely, so we include a label-based fuzzy matcher for those.
 */

(function () {
  'use strict';

  const RW = window.ResumeWingATS;

  // ── Default field selectors ───────────────────────────────────────────────

  const DEFAULTS = {
    // Ashby uses a single "name" field (combined full name)
    full_name: [
      'input[data-testid="name-input"]',
      'input[name="name"]',
      'input[placeholder*="Full name" i]',
      'input[placeholder*="Your name" i]',
      'input[autocomplete="name"]',
    ],
    // Some postings split first/last — fallback selectors
    first_name: [
      'input[data-testid="first-name-input"]',
      'input[name="firstName"]',
      'input[placeholder*="First name" i]',
      'input[autocomplete="given-name"]',
    ],
    last_name: [
      'input[data-testid="last-name-input"]',
      'input[name="lastName"]',
      'input[placeholder*="Last name" i]',
      'input[autocomplete="family-name"]',
    ],
    email: [
      'input[data-testid="email-input"]',
      'input[name="email"]',
      'input[type="email"]',
    ],
    phone: [
      'input[data-testid="phone-input"]',
      'input[name="phone"]',
      'input[type="tel"]',
      'input[placeholder*="Phone" i]',
    ],
    location: [
      'input[data-testid="location-input"]',
      'input[name="location"]',
      'input[placeholder*="Location" i]',
      'input[placeholder*="City" i]',
    ],
    linkedin: [
      'input[data-testid="linkedin-input"]',
      'input[name="linkedin"]',
      'input[placeholder*="LinkedIn" i]',
      'input[id*="linkedin" i]',
    ],
    github: [
      'input[data-testid="github-input"]',
      'input[name="github"]',
      'input[placeholder*="GitHub" i]',
      'input[id*="github" i]',
    ],
    portfolio: [
      'input[data-testid="portfolio-input"]',
      'input[name="portfolio"]',
      'input[placeholder*="Portfolio" i]',
      'input[placeholder*="Website" i]',
      'input[placeholder*="Personal site" i]',
    ],
    current_company: [
      'input[name="currentCompany"]',
      'input[placeholder*="Current company" i]',
    ],
  };

  // ── Custom question label-matching ────────────────────────────────────────

  const LABEL_MAP = [
    { patterns: [/linkedin/i],              getValue: p => p.links.linkedin   },
    { patterns: [/github/i],               getValue: p => p.links.github    },
    { patterns: [/portfolio|website/i],    getValue: p => p.links.portfolio  },
    { patterns: [/phone|mobile/i],         getValue: p => p.personal.phone   },
    { patterns: [/location|city/i],        getValue: p => [p.personal.city, p.personal.state].filter(Boolean).join(', ') },
    { patterns: [/current.*company|employer/i], getValue: p => p.work_experience?.[0]?.company ?? '' },
    { patterns: [/salary|compensation/i],  getValue: p => p.preferences?.expected_salary ?? '' },
  ];

  async function fillCustomQuestions (profile, results) {
    // Ashby wraps each question in a <div> with a <label> above the input
    const inputs = document.querySelectorAll(
      'input[type="text"]:not([data-testid]), textarea:not([data-testid])'
    );

    for (const input of inputs) {
      if (input.value) continue; // Already filled

      const labelEl =
        (input.id ? document.querySelector(`label[for="${input.id}"]`) : null) ??
        input.closest('div[class*="field"]')?.querySelector('label') ??
        input.previousElementSibling;

      const labelText = labelEl?.textContent?.trim() ?? '';
      if (!labelText) continue;

      for (const { patterns, getValue } of LABEL_MAP) {
        if (patterns.some(re => re.test(labelText))) {
          const value = getValue(profile);
          if (value && RW.fillInput(input, value)) {
            RW.highlight(input);
            results.filled.push(`custom: ${labelText.slice(0, 30)}`);
          }
          break;
        }
      }
    }
  }

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

    // ── Try full name first; if not found, use split first/last ──────────────
    const fullNameValue = [p.first_name, p.last_name].filter(Boolean).join(' ');
    const fullNameSel   = RW.fillBySelectorList(sel.full_name, fullNameValue);

    if (fullNameSel) {
      results.filled.push('full_name');
      RW.highlight(document.querySelector(fullNameSel));
    } else {
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

    // ── Standard fields ───────────────────────────────────────────────────────
    const standardFields = [
      { key: 'email',          value: p.email    },
      { key: 'phone',          value: p.phone    },
      { key: 'location',       value: [p.city, p.state].filter(Boolean).join(', ') },
      { key: 'linkedin',       value: l.linkedin },
      { key: 'github',         value: l.github   },
      { key: 'portfolio',      value: l.portfolio },
      { key: 'current_company',value: w.company  },
    ];

    for (const { key, value } of standardFields) {
      if (!value) { results.skipped.push(key); continue; }
      try {
        const matched = RW.fillBySelectorList(sel[key] ?? [], value);
        matched
          ? (results.filled.push(key), RW.highlight(document.querySelector(matched)))
          : results.skipped.push(key);
      } catch (_) {
        results.errors.push(key);
      }
    }

    // ── Fuzzy label-match for custom questions ────────────────────────────────
    await fillCustomQuestions(profile, results);

    return results;
  }

  // ── ATS detection ─────────────────────────────────────────────────────────

  function detect () {
    return (
      location.hostname.includes('ashbyhq.com') ||
      !!document.querySelector('input[data-testid="name-input"], input[data-testid="email-input"]')
    );
  }

  // ── Register module ───────────────────────────────────────────────────────
  RW.module = { name: 'Ashby', fill, detect };

})();
