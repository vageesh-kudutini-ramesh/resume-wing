/**
 * ResumeWing Autofill — Universal Field Classifier
 *
 * Runs on any job application page that isn't already handled by one of the
 * 5 platform-specific modules (Greenhouse, Lever, Workday, SmartRecruiters, Ashby).
 *
 * How it achieves near-universal coverage
 * ────────────────────────────────────────
 * Instead of hard-coded CSS selectors (which only work if you know the exact
 * HTML in advance), we classify each form field by reading its MEANING from
 * the signals that every field carries:
 *
 *   Layer 0 — Domain memory       Exact mappings learned from previous visits
 *   Layer 1 — autocomplete attr   HTML5 standard; "given-name", "email", etc.
 *   Layer 2 — type attribute       type="email", type="tel"
 *   Layer 3 — Text signal match   Label, placeholder, name, id, aria-label
 *   Layer 4 — Surrounding text    Text in nearby DOM nodes (200px radius)
 *   Layer 5 — Backend AI          Semantic similarity via sentence-transformers
 *                                  (only called for fields that scored < 45)
 *
 * Confidence thresholds
 * ─────────────────────
 *   ≥ 80  Auto-fill     → green highlight
 *   50–79 Fill + verify → yellow highlight, shown in "Please verify" section
 *   < 50  Unknown       → not filled, shown in panel for user to label
 *
 * Domain memory (the compounding flywheel)
 * ─────────────────────────────────────────
 * Every field that was confirmed (auto-fill or user-verified) is stored as
 * { domain → { selector → field_key } } in chrome.storage.local.
 * Next visit to the same domain: instant, perfectly accurate fill.
 * Users can optionally submit their learned mappings back to the GitHub repo
 * to benefit everyone — same idea as the selector remote config.
 */

(function () {
  'use strict';

  console.log('[ResumeWing] universal.js injected on:', location.href);

  const RW = window.ResumeWingATS;
  if (!RW) { console.warn('[ResumeWing] universal.js: ResumeWingATS not found — common.js missing?'); return; }

  // ── Guard: defer to platform-specific modules when available ──────────────
  // (common.js + greenhouse.js etc. run before this file)
  if (RW.module) { console.log('[ResumeWing] universal.js: deferring to platform module:', RW.module.name); return; }

  // ── No URL gate ──────────────────────────────────────────────────────────
  // Previously we returned early if the URL didn't look like a job page.
  // That blocked modal-based applies (LinkedIn-style "Easy Apply" where the
  // form lives behind a button click) and SPA pages that hadn't routed yet.
  // We now ALWAYS register the universal module — scanning is deferred to
  // when the user actually clicks "Fill" in the panel, by which point any
  // modal/SPA has rendered.
  console.log('[ResumeWing] universal.js: registering on:', location.href);


  // ═══════════════════════════════════════════════════════════════════════════
  // PATTERN LIBRARY
  // All patterns are regex, tested against the lowercase text signal.
  // Remote-config override: background.js fetches field-patterns.json from
  // GitHub and stores it in chrome.storage.local as 'rw_field_patterns'.
  // This object is the built-in default fallback.
  // ═══════════════════════════════════════════════════════════════════════════

  const FIELD_PATTERNS = {

    // ── Personal ─────────────────────────────────────────────────────────────

    first_name: {
      autocomplete: ['given-name', 'first-name', 'given name'],
      patterns: [
        /\bfirst[\s_\-.]?name\b/i, /\bgiven[\s_\-.]?name\b/i,
        /\bfname\b/i, /\bf_name\b/i, /\bforename\b/i,
        /\blegal[\s_\-.]?first\b/i, /\bapplicant[\s_\-.]?first\b/i,
        /\bfirst[\s_\-.]?nam\b/i,
      ],
    },

    last_name: {
      autocomplete: ['family-name', 'last-name', 'family name'],
      patterns: [
        /\blast[\s_\-.]?name\b/i, /\bfamily[\s_\-.]?name\b/i,
        /\bsurname\b/i, /\blname\b/i, /\bl_name\b/i,
        /\blast[\s_\-.]?nam\b/i, /\bapplicant[\s_\-.]?last\b/i,
      ],
    },

    full_name: {
      autocomplete: ['name'],
      patterns: [
        /^name$/i, /\bfull[\s_\-.]?name\b/i, /\byour[\s_\-.]?name\b/i,
        /\blegal[\s_\-.]?name\b/i, /\bapplicant[\s_\-.]?name\b/i,
        /\bcomplete[\s_\-.]?name\b/i, /\bcandidates?[\s_\-.]?name\b/i,
      ],
    },

    email: {
      type: ['email'],
      autocomplete: ['email'],
      patterns: [
        /\bemail\b/i, /\be[\s\-]?mail\b/i, /\bemail[\s_\-.]?address\b/i,
        /\bwork[\s_\-.]?email\b/i, /\bcontact[\s_\-.]?email\b/i,
        /\bpersonal[\s_\-.]?email\b/i,
      ],
    },

    phone: {
      type: ['tel'],
      autocomplete: ['tel', 'mobile', 'phone'],
      patterns: [
        /\bphone\b/i, /\bmobile\b/i, /\bcell\b/i, /\btelephone\b/i,
        /\bphone[\s_\-.]?number\b/i, /\bcontact[\s_\-.]?number\b/i,
        /\bmobile[\s_\-.]?number\b/i, /\bcell[\s_\-.]?phone\b/i,
        /\bphone[\s_\-.]?no\b/i, /\bph[\s_\-.]?no\b/i,
      ],
    },

    // ── Location ──────────────────────────────────────────────────────────────

    city: {
      autocomplete: ['address-level2'],
      patterns: [
        /^city$/i, /\bcity[\s_\-.]?of\b/i, /\btown\b/i,
        /\bmunicipality\b/i, /\bcity[\s_\-.]?name\b/i, /\bcurrent[\s_\-.]?city\b/i,
        /\bcity[\s_\-.]?residence\b/i, /\bresidence[\s_\-.]?city\b/i,
      ],
    },

    state: {
      autocomplete: ['address-level1'],
      patterns: [
        /^state$/i, /\bstate[\s_\/]province\b/i, /\bprovince\b/i,
        /\bregion\b/i, /^state[\s_\-.]?name$/i,
      ],
    },

    zip: {
      autocomplete: ['postal-code'],
      patterns: [
        /\bzip\b/i, /\bpostal[\s_\-.]?code\b/i,
        /\bpost[\s_\-.]?code\b/i, /\bpin[\s_\-.]?code\b/i,
        /\bzip[\s_\-.]?code\b/i,
      ],
    },

    country: {
      autocomplete: ['country', 'country-name'],
      patterns: [
        /^country$/i, /\bcountry[\s_\-.]?of[\s_\-.]?residence\b/i,
        /\bnationality\b/i, /\bcountry[\s_\-.]?name\b/i,
      ],
    },

    address: {
      autocomplete: ['street-address', 'address-line1'],
      patterns: [
        /\baddress[\s_\-.]?line[\s_\-.]?1\b/i, /\bstreet[\s_\-.]?address\b/i,
        /\bmailing[\s_\-.]?address\b/i, /^address[\s_\-.]?1$/i,
      ],
    },

    // ── Professional links ─────────────────────────────────────────────────────

    linkedin: {
      patterns: [
        /\blinkedin\b/i, /\blinkedin[\s_\-.]?url\b/i,
        /\blinkedin[\s_\-.]?profile\b/i, /\blinkedin[\s_\-.]?link\b/i,
        /linkedin\.com/i,
      ],
    },

    github: {
      patterns: [
        /\bgithub\b/i, /\bgithub[\s_\-.]?url\b/i,
        /\bgithub[\s_\-.]?profile\b/i, /\bgithub[\s_\-.]?link\b/i,
        /github\.com/i,
      ],
    },

    portfolio: {
      autocomplete: ['url'],
      patterns: [
        /\bportfolio\b/i, /\bpersonal[\s_\-.]?site\b/i,
        /\bpersonal[\s_\-.]?website\b/i, /\bwebsite\b/i,
        /\bblog\b/i, /\bpersonal[\s_\-.]?url\b/i,
        /\bpersonal[\s_\-.]?link\b/i, /\bhomepage\b/i,
      ],
    },

    // ── Current role ───────────────────────────────────────────────────────────

    current_company: {
      autocomplete: ['organization'],
      patterns: [
        /\bcurrent[\s_\-.]?company\b/i, /\bcurrent[\s_\-.]?employer\b/i,
        /\bemployer\b/i, /^company$/i, /^organization$/i, /^org$/i,
        /\bcurrent[\s_\-.]?org\b/i, /\bcompany[\s_\-.]?name\b/i,
        /\bmost[\s_\-.]?recent[\s_\-.]?employer\b/i,
      ],
    },

    job_title: {
      autocomplete: ['organization-title'],
      patterns: [
        /\bcurrent[\s_\-.]?title\b/i, /\bjob[\s_\-.]?title\b/i,
        /\bcurrent[\s_\-.]?role\b/i, /\bcurrent[\s_\-.]?position\b/i,
        /\byour[\s_\-.]?title\b/i, /^title$/i,
        /\bdesignation\b/i, /\brole[\s_\-.]?title\b/i,
      ],
    },

    // ── Application questions ─────────────────────────────────────────────────

    years_experience: {
      patterns: [
        /\byears[\s_\-.]?of[\s_\-.]?experience\b/i,
        /\byears[\s_\-.]?experience\b/i,
        /\bexperience[\s_\-.]?years\b/i,
        /\bhow[\s_\-.]?many[\s_\-.]?years\b/i,
        /\btotal[\s_\-.]?experience\b/i,
        /\byrs[\s_\-.]?of[\s_\-.]?exp\b/i,
      ],
    },

    expected_salary: {
      patterns: [
        /\bsalary[\s_\-.]?expectation\b/i, /\bexpected[\s_\-.]?salary\b/i,
        /\bdesired[\s_\-.]?salary\b/i, /\bcompensation\b/i,
        /\bctc\b/i, /\bexpected[\s_\-.]?ctc\b/i,
        /\bcurrent[\s_\-.]?ctc\b/i, /\bsalary[\s_\-.]?requirement\b/i,
        /\bexpected[\s_\-.]?pay\b/i, /\bpay[\s_\-.]?expectation\b/i,
      ],
    },

    notice_period: {
      patterns: [
        /\bnotice[\s_\-.]?period\b/i, /\bnotice\b/i,
        /\bweeks[\s_\-.]?notice\b/i, /\bdays[\s_\-.]?notice\b/i,
        /\bserving[\s_\-.]?notice\b/i, /\bnotice[\s_\-.]?time\b/i,
      ],
    },

    start_date: {
      patterns: [
        /\bstart[\s_\-.]?date\b/i, /\bavailable[\s_\-.]?from\b/i,
        /\bwhen[\s_\-.]?can[\s_\-.]?you[\s_\-.]?start\b/i,
        /\bearliest[\s_\-.]?start\b/i, /\bavailability\b/i,
        /\bjoining[\s_\-.]?date\b/i,
      ],
    },

    work_authorization: {
      patterns: [
        /\bwork[\s_\-.]?auth/i, /\bauthorized[\s_\-.]?to[\s_\-.]?work\b/i,
        /\beligible[\s_\-.]?to[\s_\-.]?work\b/i,
        /\bright[\s_\-.]?to[\s_\-.]?work\b/i,
        /\bwork[\s_\-.]?visa\b/i, /\bvisa[\s_\-.]?sponsorship\b/i,
        /\bsponsor/i, /\blegal[\s_\-.]?right\b/i,
        /\bcitizenship\b/i, /\bwork[\s_\-.]?permit\b/i,
      ],
    },

    how_did_you_hear: {
      patterns: [
        /\bhow[\s_\-.]?did[\s_\-.]?you[\s_\-.]?hear\b/i,
        /\breferred[\s_\-.]?by\b/i, /\breferral\b/i,
        /\bhow[\s_\-.]?did[\s_\-.]?you[\s_\-.]?find\b/i,
        /\bdiscover[\s_\-.]?us\b/i, /\bsource\b/i,
      ],
    },

    cover_letter: {
      patterns: [
        /\bcover[\s_\-.]?letter\b/i, /\bmotivation[\s_\-.]?letter\b/i,
        /\bwhy[\s_\-.]?do[\s_\-.]?you[\s_\-.]?want\b/i,
        /\btell[\s_\-.]?us[\s_\-.]?about\b/i,
        /\badditional[\s_\-.]?information\b/i,
        /\banything[\s_\-.]?else\b/i, /\bmessage\b/i,
        /\bintroduce[\s_\-.]?yourself\b/i,
      ],
    },

    // ── Education ──────────────────────────────────────────────────────────────

    school: {
      patterns: [
        /\bschool\b/i, /\buniversity\b/i, /\bcollege\b/i,
        /\binstitution\b/i, /\balma[\s_\-.]?mater\b/i,
        /\bhighest[\s_\-.]?education\b/i, /\beducation[\s_\-.]?institution\b/i,
      ],
    },

    degree: {
      patterns: [
        /\bdegree\b/i, /\bhighest[\s_\-.]?degree\b/i,
        /\blevel[\s_\-.]?of[\s_\-.]?education\b/i,
        /\beducation[\s_\-.]?level\b/i, /\bqualification\b/i,
      ],
    },

    major: {
      patterns: [
        /\bmajor\b/i, /\bfield[\s_\-.]?of[\s_\-.]?study\b/i,
        /\bconcentration\b/i, /\barea[\s_\-.]?of[\s_\-.]?study\b/i,
        /\bcourse\b/i, /\bspecialization\b/i, /\bdiscipline\b/i,
      ],
    },

    graduation_year: {
      patterns: [
        /\bgraduation[\s_\-.]?year\b/i, /\byear[\s_\-.]?of[\s_\-.]?graduation\b/i,
        /\bgraduation[\s_\-.]?date\b/i, /\bgraduated\b/i,
        /\bcompletion[\s_\-.]?year\b/i, /\bpass[\s_\-.]?out[\s_\-.]?year\b/i,
      ],
    },
  };


  // ═══════════════════════════════════════════════════════════════════════════
  // SIGNAL COLLECTION — gather all text hints a field carries
  // ═══════════════════════════════════════════════════════════════════════════

  function _getSignals (el) {
    const s = {
      type:         (el.type         || '').toLowerCase(),
      name:         (el.name         || '').toLowerCase(),
      id:           (el.id           || '').toLowerCase(),
      placeholder:  (el.placeholder  || '').toLowerCase(),
      autocomplete: (el.getAttribute('autocomplete') || '').toLowerCase(),
      ariaLabel:    (el.getAttribute('aria-label')   || '').toLowerCase(),
      ariaDesc:     (el.getAttribute('aria-describedby') || ''),
      label:        '',
      nearText:     '',
    };

    // 1. Explicit <label for="id"> association
    if (el.id) {
      try {
        const lbl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
        if (lbl) s.label = lbl.textContent.trim().toLowerCase();
      } catch (_) {}
    }

    // 2. Ancestor <label> wrapping the input
    if (!s.label) {
      const ancestor = el.closest('label');
      if (ancestor) {
        // Get the label text but exclude the input's value
        const clone = ancestor.cloneNode(true);
        clone.querySelectorAll('input,textarea,select').forEach(n => n.remove());
        s.label = clone.textContent.trim().toLowerCase();
      }
    }

    // 3. Sibling / nearby element heuristic
    if (!s.label) {
      const parent = el.parentElement;
      if (parent) {
        // Check immediate preceding sibling
        let prev = el.previousElementSibling;
        while (prev) {
          const txt = prev.textContent.trim();
          if (txt.length > 1 && txt.length < 120) {
            s.nearText = txt.toLowerCase();
            break;
          }
          prev = prev.previousElementSibling;
        }

        // Check parent's preceding sibling
        if (!s.nearText && parent.previousElementSibling) {
          const txt = parent.previousElementSibling.textContent.trim();
          if (txt.length > 1 && txt.length < 120) {
            s.nearText = txt.toLowerCase();
          }
        }
      }
    }

    // 4. aria-describedby resolution
    if (s.ariaDesc) {
      const descEl = document.getElementById(s.ariaDesc);
      if (descEl) s.nearText += ' ' + descEl.textContent.trim().toLowerCase();
    }

    return s;
  }


  // ═══════════════════════════════════════════════════════════════════════════
  // CLASSIFIER — run signals through the pattern library
  // ═══════════════════════════════════════════════════════════════════════════

  function _classify (signals, remotePatterns = {}) {
    const patterns = Object.keys(FIELD_PATTERNS).length
      ? FIELD_PATTERNS
      : remotePatterns;

    // Merge remote pattern additions into built-in defaults.
    // Skip metadata keys (e.g. _version, _instructions) from the remote JSON.
    const merged = { ...FIELD_PATTERNS };
    for (const [key, val] of Object.entries(remotePatterns)) {
      if (key.startsWith('_')) continue;
      if (!merged[key] && val && typeof val === 'object' && !Array.isArray(val)) {
        merged[key] = val;
      }
    }

    const scores = [];

    for (const [fieldKey, config] of Object.entries(merged)) {
      let confidence = 0;

      // ── Layer 1: autocomplete (guaranteed match) ────────────────────────────
      if (config.autocomplete?.length && signals.autocomplete) {
        const hit = config.autocomplete.some(ac =>
          signals.autocomplete === ac || signals.autocomplete.startsWith(ac)
        );
        if (hit) { scores.push({ fieldKey, confidence: 100 }); continue; }
      }

      // ── Layer 2: input type (high confidence) ──────────────────────────────
      if (config.type?.length && signals.type) {
        if (config.type.includes(signals.type)) {
          confidence = Math.max(confidence, 95);
        }
      }

      // ── Layer 3: pattern matching across text signals ──────────────────────
      if (config.patterns?.length) {
        const weightedSignals = [
          { text: signals.label,        weight: 90 },  // <label> text — most reliable
          { text: signals.ariaLabel,    weight: 85 },  // aria-label  — very reliable
          { text: signals.placeholder,  weight: 78 },  // placeholder — reliable
          { text: signals.name,         weight: 72 },  // name attr   — good
          { text: signals.id,           weight: 65 },  // id attr     — good
          { text: signals.nearText,     weight: 48 },  // nearby text — weaker signal
        ];

        for (const { text, weight } of weightedSignals) {
          if (!text) continue;
          // Patterns from the built-in library are RegExp objects;
          // patterns from the remote JSON config are raw strings.
          // Normalise both so .test() always works.
          const matched = config.patterns.some(re => {
            try {
              const regex = typeof re === 'string' ? new RegExp(re, 'i') : re;
              return regex.test(text);
            } catch (_) { return false; }
          });
          if (matched) confidence = Math.max(confidence, weight);
        }
      }

      if (confidence > 0) {
        scores.push({ fieldKey, confidence });
      }
    }

    // Sort by confidence descending; return best match
    scores.sort((a, b) => b.confidence - a.confidence);
    return scores[0] ?? null;
  }


  // ═══════════════════════════════════════════════════════════════════════════
  // PROFILE VALUE RESOLVER — map field key → value from the profile object
  // ═══════════════════════════════════════════════════════════════════════════

  function _getValue (fieldKey, profile) {
    const p    = profile.personal      ?? {};
    const l    = profile.links         ?? {};
    const w    = profile.work_experience?.[0] ?? {};
    const e    = profile.education?.[0]       ?? {};
    const pref = profile.preferences   ?? {};
    const meta = profile.metadata      ?? {};

    const noticeDays = parseInt(pref.notice_period_days, 10) || 0;
    const noticeWeeks = noticeDays ? `${Math.round(noticeDays / 7)} weeks` : '';

    const VALUE_MAP = {
      first_name:         p.first_name,
      last_name:          p.last_name,
      full_name:          [p.first_name, p.last_name].filter(Boolean).join(' '),
      email:              p.email,
      phone:              p.phone,
      city:               p.city,
      state:              p.state,
      zip:                p.zip,
      country:            p.country || 'United States',
      address:            '',        // too risky to auto-fill; rarely in resume
      linkedin:           l.linkedin,
      github:             l.github,
      portfolio:          l.portfolio,
      current_company:    w.company,
      job_title:          w.title,
      years_experience:   meta.years_experience ? String(meta.years_experience) : '',
      expected_salary:    pref.expected_salary || '',
      notice_period:      noticeWeeks,
      start_date:         '',        // depends on current date + notice period
      work_authorization: pref.work_authorized ? 'Yes' : 'No',
      how_did_you_hear:   '',        // personal choice; leave blank
      cover_letter:       profile.summary || '',
      school:             e.school,
      degree:             e.degree,
      major:              e.major,
      graduation_year:    e.graduation_year,
    };

    return VALUE_MAP[fieldKey] || '';
  }


  // ═══════════════════════════════════════════════════════════════════════════
  // SELECTOR GENERATOR — creates a stable CSS selector for domain memory
  // ═══════════════════════════════════════════════════════════════════════════

  function _makeSelector (el) {
    if (el.id) return `#${CSS.escape(el.id)}`;
    if (el.name) return `${el.tagName.toLowerCase()}[name="${CSS.escape(el.name)}"]`;

    // Positional fallback: nth form element
    const form = el.closest('form') || document.body;
    const inputs = Array.from(form.querySelectorAll('input,textarea,select'));
    const idx = inputs.indexOf(el);
    return `[data-rw-idx="${idx}"]`;
  }


  // ═══════════════════════════════════════════════════════════════════════════
  // PAGE SCANNER — find and classify all visible form inputs
  // ═══════════════════════════════════════════════════════════════════════════

  function _scanPage (domainMemory, remotePatterns) {
    const SKIP_TYPES = new Set([
      'hidden','submit','button','reset','checkbox','radio','file','image','color','range',
    ]);

    const inputs = document.querySelectorAll('input, textarea, select');
    const detected = [];

    for (const el of inputs) {
      if (SKIP_TYPES.has((el.type || '').toLowerCase())) continue;
      if (!_isVisible(el)) continue;

      const selector = _makeSelector(el);

      // Layer 0: domain memory — perfect recall, skip classification entirely
      if (domainMemory[selector]) {
        detected.push({
          el, selector,
          fieldKey:   domainMemory[selector],
          confidence: 100,
          source:     'memory',
        });
        continue;
      }

      const signals = _getSignals(el);
      const match   = _classify(signals, remotePatterns);

      if (match) {
        detected.push({
          el, selector,
          fieldKey:   match.fieldKey,
          confidence: match.confidence,
          source:     'classifier',
          signals,
        });
      } else {
        // Unclassified — surface for backend AI or user labeling
        detected.push({
          el, selector,
          fieldKey:   null,
          confidence: 0,
          source:     'unknown',
          signals,
        });
      }
    }

    return detected;
  }


  // ═══════════════════════════════════════════════════════════════════════════
  // MAIN FILL FUNCTION — called by content.js when user clicks "Fill"
  // ═══════════════════════════════════════════════════════════════════════════

  async function fill (profile, customOverrides = {}) {
    // Fetch domain memory + remote pattern overrides from background
    const domain = location.hostname;

    const storedData = await new Promise(resolve => {
      chrome.runtime.sendMessage({ type: 'GET_UNIVERSAL_DATA', domain }, resolve);
    });

    const domainMemory   = storedData?.domainMemory   ?? {};
    const remotePatterns = storedData?.fieldPatterns  ?? {};

    const detected = _scanPage(domainMemory, remotePatterns);

    const results = {
      filled:    [],   // { key, confidence, el, selector, verify: bool }
      skipped:   [],   // { key, reason }
      errors:    [],   // { key, error }
      uncertain: [],   // { el, selector, signals } — user must label these
      needsAI:   [],   // { el, selector, signals } — queued for backend AI call
    };

    for (const field of detected) {
      const { el, fieldKey, confidence, source, selector, signals } = field;

      // ── Unknown field — queue for AI or user labeling ─────────────────────
      if (!fieldKey || confidence === 0) {
        if (signals && (signals.label || signals.placeholder || signals.ariaLabel)) {
          results.needsAI.push({ el, selector, signals });
        }
        continue;
      }

      const value = _getValue(fieldKey, profile);

      if (!value) {
        results.skipped.push({ key: fieldKey, reason: 'no value in profile' });
        continue;
      }

      // ── High confidence (≥80) → auto-fill ─────────────────────────────────
      if (confidence >= 80) {
        try {
          const ok = RW.fillReactInput(el, value) || RW.fillInput(el, value);
          if (ok) {
            results.filled.push({ key: fieldKey, confidence, el, selector, verify: false });
            RW.highlight(el);
          } else {
            results.skipped.push({ key: fieldKey, reason: 'fill failed' });
          }
        } catch (err) {
          results.errors.push({ key: fieldKey, error: err.message });
        }
      }

      // ── Medium confidence (50–79) → fill but mark for verification ─────────
      else if (confidence >= 50) {
        try {
          const ok = RW.fillReactInput(el, value) || RW.fillInput(el, value);
          if (ok) {
            results.filled.push({ key: fieldKey, confidence, el, selector, verify: true });
            _highlightVerify(el);
          } else {
            results.skipped.push({ key: fieldKey, reason: 'fill failed' });
          }
        } catch (err) {
          results.errors.push({ key: fieldKey, error: err.message });
        }
      }

      // ── Low confidence (<50) → surface in panel as uncertain ───────────────
      else {
        results.uncertain.push({ el, selector, fieldKey, confidence, signals });
      }
    }

    // ── Backend AI classification for unknown fields ───────────────────────
    // Fire-and-forget; results come back asynchronously and update the panel
    if (results.needsAI.length > 0) {
      _classifyViaBackend(results.needsAI, profile, domain, results).catch(() => {});
    }

    return results;
  }


  // ═══════════════════════════════════════════════════════════════════════════
  // BACKEND AI CLASSIFICATION — for truly unknown fields
  // ═══════════════════════════════════════════════════════════════════════════

  async function _classifyViaBackend (unknownFields, profile, domain, results) {
    for (const { el, selector, signals } of unknownFields) {
      try {
        const res = await fetch('http://localhost:8000/profile/classify-field', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            label:          signals.label,
            placeholder:    signals.placeholder,
            name:           signals.name,
            id:             signals.id,
            aria_label:     signals.ariaLabel,
            surrounding:    signals.nearText,
          }),
        });

        if (!res.ok) continue;

        const { field_key, confidence } = await res.json();
        if (!field_key || confidence < 0.45) continue;

        const value = _getValue(field_key, profile);
        if (!value) continue;

        const ok = RW.fillReactInput(el, value) || RW.fillInput(el, value);
        if (!ok) continue;

        const confidencePct = Math.round(confidence * 100);

        if (confidence >= 0.80) {
          results.filled.push({ key: field_key, confidence: confidencePct, el, selector, verify: false, source: 'ai' });
          RW.highlight(el);
        } else {
          results.filled.push({ key: field_key, confidence: confidencePct, el, selector, verify: true, source: 'ai' });
          _highlightVerify(el);
        }

        _learnMapping(domain, selector, field_key);

      } catch (_) {
        // Backend unavailable — silently skip
      }
    }

    // The shared smart-autofill pass (radios + open questions) runs from
    // content.js after every platform module's fill, so we don't need to
    // do it here.

    // Signal content.js to re-render results with AI additions
    window.dispatchEvent(new CustomEvent('rw-ai-results-updated', { detail: results }));
  }


  // ═══════════════════════════════════════════════════════════════════════════
  // DOMAIN MEMORY — persist confirmed mappings
  // ═══════════════════════════════════════════════════════════════════════════

  function _learnMapping (domain, selector, fieldKey) {
    chrome.runtime.sendMessage({
      type: 'LEARN_MAPPING',
      domain, selector, fieldKey,
    });
  }

  // Called from content.js when user confirms/corrects a field label
  RW.learnMapping = _learnMapping;

  // Export for content.js to call after user labels an unknown field
  RW.fillField = function (el, profile, fieldKey) {
    const value = _getValue(fieldKey, profile);
    if (!value) return false;
    const ok = RW.fillReactInput(el, value) || RW.fillInput(el, value);
    if (ok) RW.highlight(el);
    return ok;
  };

  RW.getFieldValue = _getValue;


  // ═══════════════════════════════════════════════════════════════════════════
  // HELPERS
  // ═══════════════════════════════════════════════════════════════════════════

  function _highlightVerify (el) {
    if (!el) return;
    const prev = el.style.outline;
    el.style.outline   = '2px solid #facc15';   // Yellow — needs verification
    el.style.transition = 'outline 0.3s';
    setTimeout(() => { el.style.outline = prev; }, 4000);
  }

  function _isVisible (el) {
    if (el.offsetWidth === 0 && el.offsetHeight === 0) return false;
    const style = window.getComputedStyle(el);
    return style.display !== 'none'
      && style.visibility !== 'hidden'
      && parseFloat(style.opacity) > 0;
  }

  // Lightweight detection used by the panel for status reporting only —
  // we no longer use it as a hard gate. Returns true when the current DOM
  // has at least one fillable text-like input.
  function _hasFillableInputs () {
    const inputs = document.querySelectorAll(
      'input[type="text"], input[type="email"], input[type="tel"], input[type="url"], input:not([type]), textarea, select'
    );
    for (const el of inputs) {
      if (_isVisible(el)) return true;
    }
    return false;
  }


  // ── Register as universal fallback module ─────────────────────────────────
  RW.module = {
    name:   'Universal',
    fill,
    detect: _hasFillableInputs,
  };

})();
