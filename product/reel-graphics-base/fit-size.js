/* fit-size.js — COMPUTE a headline/hook size to fit, never author it (§2.2, the single most important fix).
 *
 * The hook font size must never be a magic number an agent guesses and re-guesses. Copy length changes
 * every reel, so a hardcoded px is guaranteed wrong — too small for short copy, overflowing for long copy.
 * Solve for the largest size whose MEASURED rendered ink fits the safe content width, clamped to a
 * per-role floor/ceiling. This makes type correct automatically for any copy length, any pack font, any
 * canvas, any language.
 *
 * Two folded-in holes this closes (from the pre-build review):
 *   1. FONT-LOAD: measuring before the pack font loads yields FALLBACK-font metrics -> wrong size (the same
 *      silent-fallback class as the dropped-class §2.5 bug). fitSize() awaits document.fonts.ready and
 *      REFUSES (ok:false) if the intended family is not actually active, so it never sizes against Times.
 *   2. ANIMATION: solving at rest lets a hook that GSAP pops to ~1.1x breach the safe zone mid-animation.
 *      fitSize() folds peakScale into the fit constraint (ink * peakScale <= maxWidth).
 *
 * Pure DOM; no framework. Runs in the composition page before the timeline builds.
 */
(function (root) {
  'use strict';

  // Measure the true rendered ink width of an element's text at a given size, including letter-spacing.
  // A Range around the text content gives the real ink box (more accurate than scrollWidth for tracking).
  function measureInk(el, sizePx) {
    const prev = el.style.fontSize;
    el.style.fontSize = sizePx + 'px';
    // force layout, then measure the tightest box around the actual glyphs
    let w = 0;
    try {
      const r = document.createRange();
      r.selectNodeContents(el);
      w = r.getBoundingClientRect().width;
    } catch (e) {
      w = el.getBoundingClientRect().width;
    }
    el.style.fontSize = prev;
    return w;
  }

  function firstFamily(el, family) {
    let fam = family;
    if (!fam && typeof getComputedStyle === 'function') { try { fam = getComputedStyle(el).fontFamily; } catch (e) {} }
    fam = fam || '';
    return fam.split(',')[0].trim().replace(/^["']|["']$/g, '');
  }

  // Is the intended family actually loaded/active? Guard against measuring fallback metrics.
  function familyActive(el, family, sizePx) {
    const fam = firstFamily(el, family);
    if (!fam) return true;
    try { return document.fonts.check(`${sizePx}px "${fam}"`); }
    catch (e) { return true; }   // if the API is unavailable, don't block — but the gate still checks fallback
  }

  /**
   * fitSize(el, opts) -> { ok, size, ink, reason }
   *   opts.maxWidth   required — the safe content width the ink must fit within (px)
   *   opts.min/max    clamp (px). Default min = role floor caller passes; max = maxWidth-ish.
   *   opts.family     intended font family (defaults to computed)
   *   opts.peakScale  peak animated scale to survive (default 1.0)
   *   opts.apply      if true (default), writes the winning size onto el.style.fontSize
   */
  async function fitSize(el, opts) {
    opts = opts || {};
    const maxWidth = opts.maxWidth;
    if (!(maxWidth > 0)) return { ok: false, reason: 'no-maxWidth' };
    const peak = opts.peakScale > 0 ? opts.peakScale : 1.0;
    const lo0 = Math.max(1, Math.floor(opts.min || 8));
    const hi0 = Math.max(lo0, Math.ceil(opts.max || maxWidth));

    if (document.fonts && document.fonts.ready) { try { await document.fonts.ready; } catch (e) {} }
    if (!familyActive(el, opts.family, hi0)) {
      // Do NOT compute against fallback metrics — that reintroduces the silent-fallback defect.
      return { ok: false, reason: 'font-not-loaded', family: firstFamily(el, opts.family) };
    }

    // Binary-search the largest size whose ink*peak fits maxWidth. `opts.measure` lets tests (and any
    // non-DOM caller) inject a measurer; defaults to the real DOM ink measurement above.
    const measure = opts.measure || measureInk;
    let lo = lo0, hi = hi0, best = lo0;
    for (let i = 0; i < 24 && lo <= hi; i++) {
      const mid = (lo + hi) >> 1;
      const fits = measure(el, mid) * peak <= maxWidth;
      if (fits) { best = mid; lo = mid + 1; } else { hi = mid - 1; }
    }
    const ink = measure(el, best);
    if (opts.apply !== false) el.style.fontSize = best + 'px';
    // best may be pinned at the floor and still overflow (copy too long for the floor) — report it so the
    // caller can rewrap rather than ship an overflow.
    const overflow = ink * peak > maxWidth + 0.5;
    return { ok: !overflow, size: best, ink: ink, reason: overflow ? 'floor-still-overflows' : 'ok' };
  }

  root.fitSize = fitSize;
  root.measureInk = measureInk;
  if (typeof module !== 'undefined' && module.exports) module.exports = { fitSize, measureInk };
})(typeof window !== 'undefined' ? window : globalThis);
