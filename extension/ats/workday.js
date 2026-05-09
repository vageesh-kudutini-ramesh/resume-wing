/**
 * ResumeWing Autofill — Workday ATS Module
 *
 * Covers *.myworkdayjobs.com application forms.
 *
 * Why Workday is harder than other ATS platforms
 * ───────────────────────────────────────────────
 * 1. React-controlled inputs — setting `element.value` alone won't trigger
 *    a re-render. We must invoke the React fiber's onChange directly.
 * 2. Lazy-rendered sections — form sections only appear after the user scrolls
 *    or interacts; we use MutationObserver to wait for them.
 * 3. Custom components — dropdowns, date pickers, country selectors are
 *    React components that don't map to native <select> elements.
 * 4. Multi-step form — "My Information", "My Experience", "Application
 *    Questions", "Review" are separate pages within the same SPA.
 *    We only fill the currently visible step; the user advances each step.
 *
 * Strategy
 * ────────
 * - Use `data-automation-id` attributes (stable across Workday versions).
 * - Try the React-fiber-aware fill first; fall back to standard DOM events.
 * - Wait for elements to appear before trying to fill them.
 * - Skip complex custom components (file upload, date pickers, dropdowns
 *   with search) — those need manual input for correctness.
 */

(function () {
  'use strict';

  const RW = window.ResumeWingATS;

  // ── Workday-specific fill (React-aware) ───────────────────────────────────

  function fillWD (el, value) {
    if (!el) return false;
    return RW.fillReactInput(el, value);
  }

  // ── Selector helper: find by data-automation-id ───────────────────────────
  // Returns the first <input> inside a [data-automation-id=X] container,
  // or the element itself if it's already an input.
  function wd (automationId) {
    const container = document.querySelector(`[data-automation-id="${automationId}"]`);
    if (!container) return null;
    if (container.tagName.toLowerCase() === 'input') return container;
    return container.querySelector('input, textarea');
  }

  // ── Try a list of automation-IDs or CSS selectors ─────────────────────────
  function fillWDByList (selectorList, value) {
    if (!value || !selectorList?.length) return null;

    for (const sel of selectorList) {
      let el = null;

      // Recognise [data-automation-id="X"] input shorthand: "wd:X"
      if (sel.startsWith('wd:')) {
        el = wd(sel.slice(3));
      } else {
        try {
          el = document.querySelector(sel);
          if (el && el.tagName.toLowerCase() !== 'input' && el.tagName.toLowerCase() !== 'textarea') {
            el = el.querySelector('input, textarea') ?? el;
          }
        } catch (_) {}
      }

      if (el && fillWD(el, value)) {
        return sel;
      }
    }
    return null;
  }

  // ── Default field selectors ───────────────────────────────────────────────

  const DEFAULTS = {
    first_name: [
      'wd:legalNameSection_firstName',
      'wd:firstName',
      '[aria-label*="First Name" i] input',
      'input[data-automation-id="firstName"]',
    ],
    last_name: [
      'wd:legalNameSection_lastName',
      'wd:lastName',
      '[aria-label*="Last Name" i] input',
      'input[data-automation-id="lastName"]',
    ],
    // Middle name / legal middle name (optional, skip if not on page)
    middle_name: [
      'wd:legalNameSection_middleName',
      'wd:middleName',
    ],
    email: [
      'wd:email',
      '[data-automation-id="email"] input',
      '[aria-label*="Email" i] input',
      'input[type="email"]',
    ],
    phone: [
      'wd:phone',
      '[data-automation-id="phone"] input',
      '[aria-label*="Phone" i] input',
      'input[type="tel"]',
    ],
    address_line1: [
      'wd:addressSection_addressLine1',
      'wd:streetAddressLine1',
      '[data-automation-id="addressLine1"] input',
    ],
    city: [
      'wd:addressSection_city',
      'wd:city',
      '[data-automation-id="city"] input',
    ],
    zip: [
      'wd:addressSection_postalCode',
      'wd:postalCode',
      '[data-automation-id="postalCode"] input',
    ],
    linkedin: [
      'wd:linkedIn',
      '[data-automation-id="linkedIn"] input',
      'input[placeholder*="LinkedIn" i]',
      '[aria-label*="LinkedIn" i] input',
    ],
    how_did_you_hear: [
      '[data-automation-id="referredBy"] input',
      'input[placeholder*="referral" i]',
    ],
  };

  // ── Main fill function ────────────────────────────────────────────────────

  async function fill (profile, customSelectors = {}) {
    // Merge remote overrides
    const sel = {};
    for (const key of Object.keys(DEFAULTS)) {
      sel[key] = [...(customSelectors[key] ?? []), ...DEFAULTS[key]];
    }

    const results = { filled: [], skipped: [], errors: [] };
    const p = profile.personal;
    const l = profile.links;

    // Wait briefly for React to finish rendering the current step
    await RW.sleep(500);

    const fieldMap = [
      { key: 'first_name',   value: p.first_name   },
      { key: 'middle_name',  value: p.middle_name   },
      { key: 'last_name',    value: p.last_name    },
      { key: 'email',        value: p.email        },
      { key: 'phone',        value: p.phone        },
      { key: 'address_line1',value: ''             }, // Skip — address is rarely in resume
      { key: 'city',         value: p.city         },
      { key: 'zip',          value: p.zip          },
      { key: 'linkedin',     value: l.linkedin     },
    ];

    for (const { key, value } of fieldMap) {
      if (!value) { results.skipped.push(key); continue; }

      try {
        // Wait up to 3s for the field to appear (Workday lazy-renders sections)
        let el = null;
        try {
          // Try to find it immediately first
          const found = findBySelectors(sel[key] ?? []);
          el = found;
          if (!el) {
            // Wait for it (some fields appear after scroll)
            const firstSel = sel[key]?.[0];
            if (firstSel) {
              const domSel = firstSel.startsWith('wd:')
                ? `[data-automation-id="${firstSel.slice(3)}"]`
                : firstSel;
              el = await Promise.race([
                RW.waitForElement(domSel, 2500),
                RW.sleep(2500).then(() => null),
              ]);
              // Get the actual input inside the container
              if (el && el.tagName.toLowerCase() !== 'input') {
                el = el.querySelector('input, textarea') ?? el;
              }
            }
          }
        } catch (_) {}

        if (el && fillWD(el, value)) {
          results.filled.push(key);
          RW.highlight(el);
        } else {
          results.skipped.push(key);
        }
      } catch (err) {
        results.errors.push(key);
      }

      // Small delay between fields to let React process state updates
      await RW.sleep(80);
    }

    return results;
  }

  // Helper: find first element from a list of mixed wd:/CSS selectors
  function findBySelectors (selectorList) {
    for (const sel of selectorList) {
      let el = null;
      if (sel.startsWith('wd:')) {
        el = wd(sel.slice(3));
      } else {
        try {
          el = document.querySelector(sel);
          if (el && !['input','textarea'].includes(el.tagName.toLowerCase())) {
            el = el.querySelector('input, textarea') ?? null;
          }
        } catch (_) {}
      }
      if (el) return el;
    }
    return null;
  }

  // ── ATS detection ─────────────────────────────────────────────────────────

  function detect () {
    return (
      location.hostname.includes('myworkdayjobs.com') ||
      !!document.querySelector('[data-automation-id]')
    );
  }

  // ── Register module ───────────────────────────────────────────────────────
  RW.module = { name: 'Workday', fill, detect };

})();
