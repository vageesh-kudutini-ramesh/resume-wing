/**
 * ResumeWing Autofill — Greenhouse ATS Module
 *
 * Covers boards.greenhouse.io/<company>/jobs/<id> application forms.
 *
 * Greenhouse field IDs are stable across all companies that use the platform.
 * Custom questions below the standard fields have dynamic IDs like
 * `#question_123456` and are handled by a fuzzy label-matcher.
 *
 * Selectors are listed in priority order (most specific → least specific).
 * Remote overrides from ats-selectors.json are merged in at call time.
 */

(function () {
  'use strict';

  const RW = window.ResumeWingATS;

  // ── Default field selectors ───────────────────────────────────────────────

  const DEFAULTS = {
    first_name: [
      '#first_name',
      'input[name="first_name"]',
      'input[autocomplete="given-name"]',
      'input[placeholder*="First name" i]',
    ],
    last_name: [
      '#last_name',
      'input[name="last_name"]',
      'input[autocomplete="family-name"]',
      'input[placeholder*="Last name" i]',
    ],
    email: [
      '#email',
      'input[name="email"]',
      'input[type="email"]',
    ],
    phone: [
      '#phone',
      'input[name="phone"]',
      'input[type="tel"]',
      'input[placeholder*="Phone" i]',
    ],
    linkedin: [
      'input[id*="linkedin" i]',
      'input[placeholder*="LinkedIn" i]',
      'input[name*="linkedin" i]',
    ],
    github: [
      'input[id*="github" i]',
      'input[placeholder*="GitHub" i]',
      'input[name*="github" i]',
    ],
    portfolio: [
      'input[id*="website" i]',
      'input[id*="portfolio" i]',
      'input[placeholder*="website" i]',
      'input[placeholder*="portfolio" i]',
    ],
    location: [
      'input[id*="location" i]',
      'input[placeholder*="Location" i]',
      'input[placeholder*="City" i]',
      'input[name*="location" i]',
    ],
    current_company: [
      'input[id*="company" i]',
      'input[placeholder*="Current company" i]',
      'input[name*="company" i]',
    ],
    school: [
      'input[id*="school" i]',
      'input[id*="university" i]',
      'input[placeholder*="School" i]',
    ],
    degree: [
      'input[id*="degree" i]',
      'input[placeholder*="Degree" i]',
    ],
  };

  // ── Field mapping: profile key → display name + value resolver ────────────

  function buildFieldMap (profile) {
    const p = profile.personal;
    const l = profile.links;
    const w = profile.work_experience?.[0] ?? {};  // Most recent job
    const e = profile.education?.[0]       ?? {};  // Most recent degree

    const city  = [p.city, p.state].filter(Boolean).join(', ');
    const phone = p.phone || p.phone_digits;

    return [
      { key: 'first_name',     value: p.first_name },
      { key: 'last_name',      value: p.last_name  },
      { key: 'email',          value: p.email      },
      { key: 'phone',          value: phone        },
      { key: 'location',       value: city         },
      { key: 'linkedin',       value: l.linkedin   },
      { key: 'github',         value: l.github     },
      { key: 'portfolio',      value: l.portfolio  },
      { key: 'current_company',value: w.company    },
      { key: 'school',         value: e.school     },
      { key: 'degree',         value: e.degree     },
    ];
  }

  // ── Custom question label-matching ────────────────────────────────────────
  // Greenhouse renders "additional questions" as fieldsets with a visible label.
  // We scan those labels and try to fill if the label matches a profile field.

  const LABEL_MAP = [
    { patterns: [/linkedin/i],           getValue: p => p.links.linkedin       },
    { patterns: [/github/i],             getValue: p => p.links.github         },
    { patterns: [/portfolio|website/i],  getValue: p => p.links.portfolio      },
    { patterns: [/phone|mobile/i],       getValue: p => p.personal.phone       },
    { patterns: [/city|location/i],      getValue: p => [p.personal.city, p.personal.state].filter(Boolean).join(', ') },
    { patterns: [/current company/i],    getValue: p => p.work_experience?.[0]?.company ?? '' },
    { patterns: [/salary|compensation/i],getValue: p => p.preferences?.expected_salary ?? '' },
  ];

  async function fillCustomQuestions (profile, results) {
    // Greenhouse wraps custom questions in `.field[id^="question_"]` containers
    const questionFields = document.querySelectorAll(
      '.field input[type="text"], .field textarea, [id^="question_"] input, [id^="question_"] textarea'
    );

    for (const input of questionFields) {
      // Find the label associated with this input
      const labelEl =
        (input.id ? document.querySelector(`label[for="${input.id}"]`) : null) ??
        input.closest('.field')?.querySelector('label') ??
        input.closest('fieldset')?.querySelector('legend');

      const labelText = labelEl?.textContent?.trim() ?? '';
      if (!labelText) continue;

      // Already filled by the main loop
      if (input.value) continue;

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
    // Merge remote overrides on top of defaults (remote wins)
    const sel = {};
    for (const key of Object.keys(DEFAULTS)) {
      sel[key] = [
        ...(customSelectors[key] ?? []),
        ...DEFAULTS[key],
      ];
    }

    const results = { filled: [], skipped: [], errors: [] };
    const fieldMap = buildFieldMap(profile);

    for (const { key, value } of fieldMap) {
      if (!value) { results.skipped.push(key); continue; }

      try {
        const matched = RW.fillBySelectorList(sel[key] ?? [], value);
        if (matched) {
          results.filled.push(key);
          RW.highlight(document.querySelector(matched));
        } else {
          results.skipped.push(key);
        }
      } catch (err) {
        results.errors.push(key);
      }
    }

    // Try to fill custom / additional questions
    await fillCustomQuestions(profile, results);

    return results;
  }

  // ── ATS detection ─────────────────────────────────────────────────────────

  function detect () {
    return (
      location.hostname.includes('greenhouse.io') ||
      !!document.querySelector('#application-form, form#application-form, [data-source="greenhouse"]')
    );
  }

  // ── Register module ───────────────────────────────────────────────────────
  RW.module = { name: 'Greenhouse', fill, detect };

})();
