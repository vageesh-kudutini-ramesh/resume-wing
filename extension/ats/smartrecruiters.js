/**
 * ResumeWing Autofill — SmartRecruiters ATS Module
 *
 * Covers jobs.smartrecruiters.com and *.smartrecruiters.com application forms.
 *
 * SmartRecruiters uses a mix of:
 * - `name` attributes on classic inputs (older job postings)
 * - `data-testid` attributes on newer React-rendered forms
 *
 * Both are listed in the selector fallback chain below.
 * Social/portfolio links appear as labelled textboxes in the "Links" section.
 */

(function () {
  'use strict';

  const RW = window.ResumeWingATS;

  // ── Default field selectors ───────────────────────────────────────────────

  const DEFAULTS = {
    first_name: [
      'input[name="firstName"]',
      '[data-testid="firstName"] input',
      '[data-testid="firstName"]',
      'input[id*="firstName" i]',
      'input[placeholder*="First name" i]',
      'input[autocomplete="given-name"]',
    ],
    last_name: [
      'input[name="lastName"]',
      '[data-testid="lastName"] input',
      '[data-testid="lastName"]',
      'input[id*="lastName" i]',
      'input[placeholder*="Last name" i]',
      'input[autocomplete="family-name"]',
    ],
    email: [
      'input[name="email"]',
      '[data-testid="email"] input',
      '[data-testid="email"]',
      'input[type="email"]',
    ],
    phone: [
      'input[name="phoneNumber"]',
      '[data-testid="phoneNumber"] input',
      '[data-testid="phoneNumber"]',
      'input[type="tel"]',
      'input[placeholder*="Phone" i]',
    ],
    linkedin: [
      'input[name="web.LinkedIn"]',
      '[data-testid="LinkedInUrl"] input',
      'input[placeholder*="LinkedIn" i]',
      'input[id*="linkedin" i]',
    ],
    github: [
      'input[name="web.GitHub"]',
      'input[placeholder*="GitHub" i]',
      'input[id*="github" i]',
    ],
    portfolio: [
      'input[name="web.Portfolio"]',
      'input[name="web.Website"]',
      '[data-testid="portfolioUrl"] input',
      'input[placeholder*="Portfolio" i]',
      'input[placeholder*="Website" i]',
    ],
    location: [
      'input[name="location"]',
      '[data-testid="location"] input',
      'input[placeholder*="Location" i]',
      'input[placeholder*="City" i]',
    ],
    current_company: [
      'input[name="experience.company"]',
      'input[placeholder*="Current company" i]',
    ],
    summary: [
      'textarea[name="message"]',
      'textarea[placeholder*="cover letter" i]',
      'textarea[placeholder*="message" i]',
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

    const fieldMap = [
      { key: 'first_name',     value: p.first_name },
      { key: 'last_name',      value: p.last_name  },
      { key: 'email',          value: p.email      },
      { key: 'phone',          value: p.phone      },
      { key: 'location',       value: [p.city, p.state].filter(Boolean).join(', ') },
      { key: 'linkedin',       value: l.linkedin   },
      { key: 'github',         value: l.github     },
      { key: 'portfolio',      value: l.portfolio  },
      { key: 'current_company',value: w.company    },
    ];

    for (const { key, value } of fieldMap) {
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

    return results;
  }

  // ── ATS detection ─────────────────────────────────────────────────────────

  function detect () {
    return (
      location.hostname.includes('smartrecruiters.com') ||
      !!document.querySelector('[data-testid="firstName"], input[name="firstName"]')
    );
  }

  // ── Register module ───────────────────────────────────────────────────────
  RW.module = { name: 'SmartRecruiters', fill, detect };

})();
