#!/usr/bin/env python3
"""
capture_site.py — Website capture with Playwright (on-demand)

Renders a site in headless Chromium, dismisses common cookie/consent banners,
and either:

  - saves a few viewport-sized frames spread top to bottom (readable, unlike
    one unreadable full-page PNG) plus the computed styles of typical
    elements, read from the live DOM; or
  - with --selector, screenshots just that element's bounding box and saves
    its outerHTML (element mode); or
  - with --motion, sweeps real states and motion, and reports what actually
    changed, not a guess: forcing :hover/:active/:focus; scrolling elements
    below the fold into view to catch IntersectionObserver-style reveals;
    clicking anything that looks like a toggle (aria-expanded/pressed/
    selected, data-state, dialogs, menus, tabs, and aria-controls targets —
    not just the element clicked, but whatever it opens elsewhere in the
    DOM) to catch JS-driven open/close and selected states; and reading
    [disabled]/[aria-disabled] styling directly, no click needed. Also flags
    native CSS scroll-driven animations (animation-timeline: scroll()/
    view()), visible <canvas>/sticky scroll-runway elements, and any detected
    motion-library signature; or
  - with --inspect-canvas, detects visible <canvas> elements (2D/WebGL),
    saves the page's loaded JS bundles to disk, and prints a capped digest of
    where the canvas selector, getContext, requestAnimationFrame, and warp/
    projection math live — queryable offline via --search-bundles <REGEX>; or
  - with --scroll-scrub, detects sticky scroll-pinned containers (like a
    carousel or story reel inside a tall scroll wrapper) and captures key
    progress frames (p=0.00 rest, p=0.07 mid-transition k≈0.35, p=0.20 next
    rest, p=0.50, p=1.00) plus a <canvas> center-vs-edge vertical span
    profile without needing ffmpeg; or
  - with --compare <ref.png>, renders at the reference screenshot's size and
    produces a 3-panel visual diff (Reference | Rebuild | 50% Onion-Skin +
    delta highlight) plus regional similarity and horizontal reach metrics; or
  - with --find-assets, finds inline-SVG illustrations (by viewBox area, so
    real artwork is told apart from icons) and real <img>/background-image
    assets, and extracts the SVGs to files — the one capture technique here
    that sees custom graphics, which every other pass is blind to because
    they're markup, not a src URL.

Page coverage: capture_frames always prints what percent of the page's full
scroll height the requested --frames actually covered, and warns loudly
with the exact --frames value needed for 100% when it falls short. A
capture that silently covers 60% of a tall page is the most expensive kind
of incomplete result, because nothing about the output looks incomplete.

Basic usage:
    python capture_site.py https://example.com

Multi-viewport:
    python capture_site.py https://example.com --viewports desktop,mobile

Element capture:
    python capture_site.py https://example.com --selector "header.navbar" -o element.png

Motion and state capture (pseudo-class, scroll-reveal, toggles, disabled):
    python capture_site.py https://example.com --motion --selector ".pricing-card, button.cta"

Inspect <canvas> and extract JS bundle math (then search offline):
    python capture_site.py https://example.com --inspect-canvas --bundles-out ./bundles
    python capture_site.py --search-bundles "warp|scaleY|getContext" --bundles-out ./bundles

Scrub a sticky scroll-pinned section across rest and mid-transition states:
    python capture_site.py https://example.com --scroll-scrub --selector ".story"

Compare a live local rebuild against a reference screenshot:
    python capture_site.py http://localhost:8090 --compare ./ref.png -o ./rebuild.png

Find and extract inline-SVG illustrations and real images:
    python capture_site.py https://example.com --find-assets --asset-out assets

Requirements:
    pip install playwright
    playwright install chromium
"""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib import request as urlrequest
from urllib.parse import urljoin, urlparse

VIEWPORT_PRESETS = {"desktop": (1440, 900), "tablet": (768, 1024), "mobile": (375, 812)}
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
COOKIE_ACCEPT_SELECTORS = [
    'button[id*="accept" i]', 'button[id*="agree" i]', 'button[id*="consent" i]',
    'button[class*="accept" i]', 'button[aria-label*="accept" i]', '[data-testid*="accept" i]',
    '#onetrust-accept-btn-handler', '.cc-accept', '.cc-allow', '.cookie-accept', '.gdpr-accept',
]
DEFAULT_MOTION_SELECTOR = 'a[href], button, [role="button"]'
DEFAULT_SCROLL_SELECTOR = (
    'section, article, [data-aos], [class*="reveal" i], [class*="fade-in" i], '
    '[class*="fade-up" i], [class*="animate-on-scroll" i], [class*="aos-" i]'
)
DEFAULT_TOGGLE_SELECTOR = (
    '[aria-expanded], [aria-pressed], [data-state], [aria-haspopup], [aria-controls], '
    '[role="tab"], summary'
)
DEFAULT_DISABLED_SELECTOR = ':disabled, [aria-disabled="true"], [data-disabled], [data-disabled="true"]'

STYLE_PROBE_JS = r"""
() => {
  const pick = ['font-family','font-size','font-weight','line-height','letter-spacing','color',
                'background-color','border-radius','padding','border','box-shadow'];
  const visible = el => { const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
  const describe = el => { const cs = getComputedStyle(el); const out = [];
    for (const p of pick) { const v = cs.getPropertyValue(p); if (v && v !== 'none' && v !== 'normal') out.push(`${p}: ${v}`); }
    return out.join('; '); };
  const lines = [];
  const once = (label, selector, limit = 1) => {
    let n = 0;
    for (const el of document.querySelectorAll(selector)) {
      if (n >= limit || !visible(el)) continue;
      n++;
      const text = (el.innerText || el.value || '').trim().replace(/\s+/g, ' ').slice(0, 28);
      lines.push(`${label}${text ? ` "${text}"` : ''}: ${describe(el)}`);
    }
  };
  once('body', 'body');
  ['h1', 'h2', 'h3'].forEach(h => once(h, h));
  once('button', 'button, a[class*="button" i], [role="button"]', 3);
  once('card', '[class*="card" i]', 2);
  return lines;
}
"""

LIBRARY_SIGNATURE_JS = r"""
() => {
  const found = [];
  if (window.gsap || window.TweenMax || window.TimelineMax) found.push('GSAP (global object present)');
  if (document.querySelector('[data-aos]')) found.push('AOS (data-aos attributes present)');
  if (document.querySelector('lottie-player')) found.push('Lottie (<lottie-player> element present)');
  if (document.querySelector('[style*="transform"][class*="framer" i]') || window.__FRAMER_DATA__)
    found.push('Framer Motion (framer-prefixed classes or runtime data present)');
  if (window.THREE) found.push('Three.js (window.THREE present)');
  if (window.PIXI) found.push('PixiJS (window.PIXI present)');
  const visibleCanvases = Array.from(document.querySelectorAll('canvas')).filter(c => {
    const r = c.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(c).visibility !== 'hidden';
  });
  if (visibleCanvases.length)
    found.push(`Procedural <canvas> (${visibleCanvases.length} visible — run with --inspect-canvas to extract JS math)`);
  const stickyRunways = Array.from(document.querySelectorAll('body *')).filter(el => {
    if (getComputedStyle(el).position !== 'sticky') return false;
    const p = el.parentElement;
    return p && (p.offsetHeight - window.innerHeight) > 200;
  });
  if (stickyRunways.length)
    found.push(`Sticky scroll-pinned runway (${stickyRunways.length} found — run with --scroll-scrub to capture rest & mid-transition states)`);
  return found;
}
"""

CANVAS_PROBE_JS = r"""
(scopeSelector) => {
  const visible = el => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden';
  };
  const cssPath = el => {
    if (el.id) return `#${el.id}`;
    const parts = [];
    for (let n = el, depth = 0; n && n.tagName && depth < 3; depth++, n = n.parentElement) {
      let part = n.tagName.toLowerCase();
      if (n.className && typeof n.className === 'string' && n.className.trim())
        part += '.' + n.className.trim().split(/\s+/)[0];
      parts.unshift(part);
    }
    return parts.join(' > ');
  };
  const nearbyLabel = el => {
    for (let n = el, depth = 0; n && depth < 4; depth++, n = n.parentElement) {
      const aria = n.getAttribute && n.getAttribute('aria-label');
      if (aria) return aria.trim().slice(0, 48);
      const heading = n.querySelector && n.querySelector('h1,h2,h3,h4,h5,h6');
      if (heading && heading.textContent.trim()) return heading.textContent.trim().slice(0, 48);
    }
    return null;
  };
  const stickyInfo = el => {
    for (let n = el; n && n !== document.body; n = n.parentElement) {
      if (getComputedStyle(n).position === 'sticky' && n.parentElement) {
        const track = n.parentElement;
        const runway = Math.max(0, track.offsetHeight - window.innerHeight);
        if (runway > 80) {
          return {
            stickySelector: cssPath(n),
            trackSelector: cssPath(track),
            trackHeight: Math.round(track.offsetHeight),
            runwayPx: Math.round(runway),
          };
        }
      }
    }
    return null;
  };

  let roots = [document];
  if (scopeSelector) {
    const matched = Array.from(document.querySelectorAll(scopeSelector));
    if (matched.length) roots = matched;
  }
  const seen = new Set();
  const canvases = [];
  for (const root of roots) {
    const list = [];
    if (root.tagName && root.tagName.toLowerCase() === 'canvas') list.push(root);
    if (root.querySelectorAll) list.push(...root.querySelectorAll('canvas'));
    for (const c of list) {
      if (seen.has(c) || !visible(c)) continue;
      seen.add(c);
      const r = c.getBoundingClientRect();
      canvases.push({
        selector: cssPath(c),
        id: c.id || null,
        className: (typeof c.className === 'string' && c.className.trim()) ? c.className.trim() : null,
        attrWidth: c.width,
        attrHeight: c.height,
        cssWidth: Math.round(r.width),
        cssHeight: Math.round(r.height),
        label: nearbyLabel(c),
        sticky: stickyInfo(c),
      });
    }
  }

  const inlineScripts = [];
  document.querySelectorAll('script:not([src])').forEach((s, idx) => {
    const text = (s.textContent || '').trim();
    if (text.length > 40) inlineScripts.push({ name: `inline-script-${idx + 1}.js`, content: text });
  });

  const scriptUrls = new Set();
  document.querySelectorAll('script[src]').forEach(s => {
    if (s.src) scriptUrls.add(s.src);
  });
  if (window.performance && performance.getEntriesByType) {
    for (const entry of performance.getEntriesByType('resource')) {
      if (entry.name && (entry.initiatorType === 'script' || /\.m?js(\?|$)/i.test(entry.name))) {
        scriptUrls.add(entry.name);
      }
    }
  }

  return {
    canvases,
    inlineScripts,
    scriptUrls: Array.from(scriptUrls),
  };
}
"""

SCROLL_SCRUB_LOCATE_JS = r"""
(targetSelector) => {
  const cssPath = el => {
    if (!el) return null;
    if (el.id) return `#${el.id}`;
    const parts = [];
    for (let n = el, depth = 0; n && n.tagName && depth < 3; depth++, n = n.parentElement) {
      let part = n.tagName.toLowerCase();
      if (n.className && typeof n.className === 'string' && n.className.trim())
        part += '.' + n.className.trim().split(/\s+/)[0];
      parts.unshift(part);
    }
    return parts.join(' > ');
  };

  const vh = window.innerHeight;
  let stickyEl = null;
  let trackEl = null;

  if (targetSelector) {
    const el = document.querySelector(targetSelector);
    if (el) {
      // Check if el itself or an ancestor is sticky, or if el contains a sticky child
      for (let n = el; n && n !== document.body; n = n.parentElement) {
        if (getComputedStyle(n).position === 'sticky' && n.parentElement && n.parentElement.offsetHeight > vh * 1.15) {
          stickyEl = n;
          trackEl = n.parentElement;
          break;
        }
      }
      if (!stickyEl) {
        const childSticky = Array.from(el.querySelectorAll('*')).find(
          c => getComputedStyle(c).position === 'sticky'
        );
        if (childSticky) {
          stickyEl = childSticky;
          trackEl = childSticky.parentElement || el;
        } else if (el.offsetHeight > vh * 1.2) {
          trackEl = el;
        }
      }
    }
  }

  if (!trackEl) {
    // Auto-detect first sticky element with a meaningful scroll runway
    for (const el of document.querySelectorAll('body *')) {
      if (getComputedStyle(el).position === 'sticky' && el.parentElement) {
        const p = el.parentElement;
        if (p.offsetHeight - vh > 150) {
          stickyEl = el;
          trackEl = p;
          break;
        }
      }
    }
  }

  if (trackEl) {
    const rect = trackEl.getBoundingClientRect();
    const trackTop = Math.round(rect.top + window.scrollY);
    const trackHeight = Math.round(trackEl.offsetHeight);
    const runwayPx = Math.max(0, trackHeight - vh);
    const canvasEl = (stickyEl || trackEl).querySelector('canvas');
    return {
      mode: stickyEl ? 'sticky-runway' : 'element-runway',
      stickySelector: cssPath(stickyEl),
      trackSelector: cssPath(trackEl),
      canvasSelector: cssPath(canvasEl),
      trackTop,
      trackHeight,
      viewportHeight: vh,
      runwayPx,
    };
  }

  const docHeight = Math.round(document.documentElement.scrollHeight);
  return {
    mode: 'document-fallback',
    stickySelector: null,
    trackSelector: 'document.documentElement',
    canvasSelector: cssPath(document.querySelector('canvas')),
    trackTop: 0,
    trackHeight: docHeight,
    viewportHeight: vh,
    runwayPx: Math.max(0, docHeight - vh),
  };
}
"""

CANVAS_SLICE_PROFILE_JS = r"""
(canvasSelector) => {
  const c = canvasSelector ? document.querySelector(canvasSelector) : document.querySelector('canvas');
  if (!c) return null;
  try {
    const w = c.width, h = c.height;
    if (!w || !h) return null;
    const off = document.createElement('canvas');
    off.width = w;
    off.height = h;
    const ctx = off.getContext('2d');
    ctx.drawImage(c, 0, 0);
    const data = ctx.getImageData(0, 0, w, h).data;
    // Estimate corner background
    const px = (x, y) => {
      const i = (Math.min(h - 1, Math.max(0, y)) * w + Math.min(w - 1, Math.max(0, x))) * 4;
      return [data[i], data[i + 1], data[i + 2], data[i + 3]];
    };
    const bg = px(2, 2);
    const colSpan = (xFrac) => {
      const x = Math.floor(w * xFrac);
      let topY = h, botY = 0;
      for (let y = 0; y < h; y += 2) {
        const p = px(x, y);
        const diff = Math.abs(p[0] - bg[0]) + Math.abs(p[1] - bg[1]) + Math.abs(p[2] - bg[2]) + Math.abs(p[3] - bg[3]);
        if (diff > 28 && p[3] > 20) {
          if (y < topY) topY = y;
          if (y > botY) botY = y;
        }
      }
      if (topY > botY) return 0;
      return Math.round(((botY - topY) / h) * 100);
    };
    const leftPct = colSpan(0.12);
    const centerPct = colSpan(0.50);
    const rightPct = colSpan(0.88);
    const edgeAvg = (leftPct + rightPct) / 2;
    const ratio = centerPct > 0 ? Number((edgeAvg / centerPct).toFixed(2)) : null;
    return { leftPct, centerPct, rightPct, edgeToCenterRatio: ratio };
  } catch (e) {
    return null;
  }
}
"""

# Default icon-vs-illustration cutoff. A typical UI icon is 16-32px / viewBox area
# under ~1,200px²; a real illustration (the kind that's invisible to every other
# capture technique here, because it's inline markup, not a src URL) runs into the
# tens of thousands. 2,500px² sits below "a big icon" and above "a tiny one".
MIN_SVG_AREA = 2500
MIN_IMG_SIZE = 64

FIND_ASSETS_JS = r"""
({ minSvgArea, minImgSize }) => {
  const visible = el => { const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
  const nearbyLabel = el => {
    // Walk up a few ancestors looking for a heading, aria-label, alt-bearing sibling,
    // or any short text node near this element — whatever gives a human a handle on
    // "which thing is this" without reading the markup.
    for (let n = el, depth = 0; n && depth < 4; depth++, n = n.parentElement) {
      const aria = n.getAttribute && n.getAttribute('aria-label');
      if (aria) return aria.trim().slice(0, 48);
      const heading = n.querySelector && n.querySelector('h1,h2,h3,h4,h5,h6');
      if (heading && heading.textContent.trim()) return heading.textContent.trim().slice(0, 48);
      const text = (n.textContent || '').trim();
      if (text && text.length < 60) return text.slice(0, 48);
    }
    return null;
  };
  const cssPath = el => {
    if (el.id) return `#${el.id}`;
    const parts = [];
    for (let n = el, depth = 0; n && n.tagName && depth < 3; depth++, n = n.parentElement) {
      let part = n.tagName.toLowerCase();
      if (n.className && typeof n.className === 'string') part += '.' + n.className.trim().split(/\s+/)[0];
      parts.unshift(part);
    }
    return parts.join(' > ');
  };

  const svgs = [];
  for (const el of document.querySelectorAll('svg')) {
    if (!visible(el)) continue;
    const vb = el.getAttribute('viewBox');
    let area = 0;
    if (vb) {
      const p = vb.split(/\s+/).map(Number);
      area = (p[2] || 0) * (p[3] || 0);
    } else {
      const r = el.getBoundingClientRect();
      area = r.width * r.height;
    }
    if (area < minSvgArea) continue; // an icon, not an illustration
    svgs.push({ selector: cssPath(el), area: Math.round(area), label: nearbyLabel(el), outerHTML: el.outerHTML });
  }

  const images = [];
  for (const el of document.querySelectorAll('img')) {
    if (!visible(el) || !el.naturalWidth) continue;
    if (el.naturalWidth < minImgSize && el.naturalHeight < minImgSize) continue; // an icon
    images.push({
      src: el.currentSrc || el.src, alt: el.alt || null,
      naturalWidth: el.naturalWidth, naturalHeight: el.naturalHeight,
      label: nearbyLabel(el), selector: cssPath(el),
    });
  }

  const bgImages = [];
  for (const el of document.querySelectorAll('body *')) {
    if (!visible(el)) continue;
    const bg = getComputedStyle(el).backgroundImage;
    if (bg && bg !== 'none' && bg.includes('url(')) {
      const r = el.getBoundingClientRect();
      if (r.width < minImgSize && r.height < minImgSize) continue;
      bgImages.push({ selector: cssPath(el), css: bg.slice(0, 200), width: Math.round(r.width), height: Math.round(r.height), label: nearbyLabel(el) });
    }
  }

  return { svgCount: svgs.length, svgs, imageCount: images.length, images, bgImageCount: bgImages.length, bgImages };
}
"""


def check_playwright_installed():
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        print(
            "Playwright is not installed.\n\nInstall with:\n\n"
            "    pip install playwright\n    playwright install chromium\n",
            file=sys.stderr,
        )
        return False


def parse_viewports_list(s):
    out = []
    for item in s.split(","):
        item = item.strip()
        if not item:
            continue
        if item in VIEWPORT_PRESETS:
            out.append((item, VIEWPORT_PRESETS[item]))
        else:
            try:
                w, h = item.lower().split("x")
                out.append((f"{w}x{h}", (int(w), int(h))))
            except Exception:
                raise argparse.ArgumentTypeError(f"Invalid viewport: {item}")
    return out or [("desktop", VIEWPORT_PRESETS["desktop"])]


def dismiss_cookie_banner(page):
    for selector in COOKIE_ACCEPT_SELECTORS:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0 and locator.is_visible(timeout=500):
                locator.click(timeout=1000)
                page.wait_for_timeout(500)
                return True
        except Exception:
            continue
    return False


def scroll_through_page(page, steps=(0.25, 0.5, 0.75, 1.0), pause_ms=400):
    try:
        height = page.evaluate("document.body.scrollHeight")
    except Exception:
        return
    for step in steps:
        page.evaluate(f"window.scrollTo(0, {int(height * step)})")
        page.wait_for_timeout(pause_ms)
    page.evaluate("window.scrollTo(0, 0)")


def capture_frames(page, base_path, viewport, frames):
    try:
        height = page.evaluate("document.documentElement.scrollHeight")
    except Exception:
        height = viewport[1]
    max_scroll = max(0, height - viewport[1])
    count = max(1, min(frames, 1 + max_scroll // max(1, viewport[1] // 2)))
    positions = [0] if count == 1 else [round(max_scroll * i / (count - 1)) for i in range(count)]
    paths = []
    stem, suffix = base_path.stem, base_path.suffix or ".png"
    for i, top in enumerate(positions, 1):
        page.evaluate(f"window.scrollTo(0, {top})")
        page.wait_for_timeout(400)
        path = base_path.with_name(f"{stem}-{i:02d}{suffix}")
        page.screenshot(path=str(path))
        paths.append(path)
    page.evaluate("window.scrollTo(0, 0)")

    # Full coverage = every viewport-height band gets at least one frame overlapping it.
    # Below that, sections genuinely go unseen — this is what silently produced an
    # incomplete capture before, so it's a loud warning now, not a quiet default.
    full_coverage_frames = max(1, -(-height // viewport[1]))  # ceil division
    coverage_pct = min(100, round(len(paths) / full_coverage_frames * 100))
    print(f"   Page height: {height}px, {len(paths)} frame(s) of {viewport[0]}x{viewport[1]} — ~{coverage_pct}% of the page")
    if coverage_pct < 90:
        print(f"   ⚠ This misses real content. Pass --frames {full_coverage_frames} for full coverage"
              f" (or --full-page for one tall screenshot, readable only at low zoom).")
    return paths


def read_motion_props(locator):
    """Properties that matter across every trigger type: pseudo-class, scroll-reveal,
    and click-toggle all commonly animate opacity/transform, accordions commonly
    animate max-height, and animationTimeline is how to spot a native CSS
    scroll-driven animation without needing to scroll at all."""
    return locator.evaluate(
        """el => { const cs = getComputedStyle(el); return {
            transition: `${cs.transitionProperty}|${cs.transitionDuration}|${cs.transitionTimingFunction}`,
            animation: cs.animationName === 'none' ? null :
              `${cs.animationName}|${cs.animationDuration}|${cs.animationTimingFunction}|${cs.animationIterationCount}`,
            animationTimeline: cs.animationTimeline && cs.animationTimeline !== 'auto' ? cs.animationTimeline : null,
            transform: cs.transform,
            opacity: cs.opacity,
            filter: cs.filter,
            maxHeight: cs.maxHeight,
            visibility: cs.visibility,
            className: el.className || null,
        }}"""
    )


def diff_states(resting, forced):
    """Generic diff over every key both reads share — new properties added to
    read_motion_props are picked up automatically, nothing to update here."""
    changed = {}
    for key in resting:
        if key in forced and resting[key] != forced[key]:
            changed[key] = {"resting": resting[key], key: forced[key]}
    return changed


def element_label(el, index):
    try:
        text = (el.inner_text(timeout=500) or el.get_attribute("aria-label") or "").strip()[:40]
        return text or f"[{index}]"
    except Exception:
        return f"[{index}]"


def capture_pseudo_class_motion(page, selector, max_elements):
    """Forces :hover, :active, and :focus — the three real CSS pseudo-classes
    a browser can apply — and diffs the computed style against resting."""
    selector = selector or DEFAULT_MOTION_SELECTOR
    locators = page.locator(selector)
    count = min(locators.count(), max_elements)
    results = []

    for i in range(count):
        el = locators.nth(i)
        try:
            el.scroll_into_view_if_needed(timeout=2000)
            resting = read_motion_props(el)
        except Exception:
            continue
        label = element_label(el, i)
        entry = {"element": label, "resting": resting, "hover": {}, "active": {}, "focus": {}}

        try:
            el.hover(timeout=1500)
            page.wait_for_timeout(120)
            entry["hover"] = diff_states(resting, read_motion_props(el))
        except Exception:
            pass

        try:
            box = el.bounding_box()
            if box:
                page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                page.mouse.down()
                page.wait_for_timeout(120)
                entry["active"] = diff_states(resting, read_motion_props(el))
                # Release away from the element, not on top of it: a down+up at the same
                # point on an <a> is a real click and can navigate the page. Moving first
                # keeps the :active read but never completes a click.
                page.mouse.move(0, 0)
                page.mouse.up()
        except Exception:
            pass

        try:
            page.mouse.move(0, 0)
            el.focus(timeout=1500)
            page.wait_for_timeout(120)
            entry["focus"] = diff_states(resting, read_motion_props(el))
            page.evaluate("document.activeElement && document.activeElement.blur()")
        except Exception:
            pass

        if entry["hover"] or entry["active"] or entry["focus"] or resting.get("animationTimeline"):
            results.append(entry)

    return results


def capture_scroll_reveal(page, selector, max_elements):
    """Finds elements currently below the fold, scrolls each into view — a
    real scroll, which is what IntersectionObserver-based reveal libraries
    (and AOS-style data attributes) actually listen for — and diffs the
    style read before against after. This is the pass that answers "what
    animates on scroll", which no pseudo-class can ever trigger."""
    page.evaluate("window.scrollTo(0, 0)")
    viewport_height = page.evaluate("window.innerHeight")
    selector = selector or DEFAULT_SCROLL_SELECTOR
    locators = page.locator(selector)
    total = locators.count()

    below_fold = []
    for i in range(total):
        el = locators.nth(i)
        try:
            box = el.bounding_box()
        except Exception:
            continue
        if box and box["y"] > viewport_height:
            below_fold.append(i)
        if len(below_fold) >= max_elements:
            break

    results = []
    for i in below_fold:
        el = locators.nth(i)
        try:
            resting = read_motion_props(el)
        except Exception:
            continue
        label = element_label(el, i)
        try:
            el.scroll_into_view_if_needed(timeout=2000)
            page.wait_for_timeout(500)
            revealed = read_motion_props(el)
        except Exception:
            continue
        changes = diff_states(resting, revealed)
        if changes:
            results.append({"element": label, "resting": resting, "revealed": changes})

    page.evaluate("window.scrollTo(0, 0)")
    return {"results": results, "belowFoldCandidates": len(below_fold)}


def navigates_on_click(el):
    """A toggle attribute on an <a href=...> is common (an expandable nav
    link) but clicking it navigates instead of just toggling — skip those
    rather than letting a probe click carry the browser to another page."""
    try:
        return bool(el.evaluate(
            """el => { const a = el.closest('a[href]'); if (!a) return false;
                const href = a.getAttribute('href') || '';
                return href !== '' && !href.startsWith('#') && !href.startsWith('javascript:'); }"""
        ))
    except Exception:
        return False


def capture_click_toggles(page, selector, max_elements):
    """Elements that advertise their own open/closed or selected state via ARIA or a
    data-state attribute are the reliable, selector-free way to find JS-driven
    toggles (accordions, disclosures, menus, tabs) without guessing at a site's
    class naming. Click once to flip the state, diff, click again best-effort to
    restore it. Every click is guarded against navigation — a toggle that's
    secretly a link can carry the browser to another page entirely, which would
    silently corrupt everything captured after it.

    Two things this covers that a narrower aria-expanded/aria-pressed-only sweep
    misses: `aria-selected` (how a tab announces which one is active — clicking it
    doesn't touch aria-expanded or aria-pressed at all), and `aria-controls`, which
    names a *different* element that actually opens or closes — a menu trigger's
    own attributes can look unchanged while the menu it controls becomes visible."""
    original_url = page.url
    selector = selector or DEFAULT_TOGGLE_SELECTOR
    locators = page.locator(selector)
    count = min(locators.count(), max_elements)
    results = []
    STATE_ATTRS = ("aria-expanded", "aria-pressed", "aria-selected", "data-state")

    for i in range(count):
        el = locators.nth(i)
        try:
            el.scroll_into_view_if_needed(timeout=2000)
            if navigates_on_click(el):
                continue
            resting = read_motion_props(el)
            state_attr = next((a for a in STATE_ATTRS if el.get_attribute(a) is not None), None)
            before_state = el.get_attribute(state_attr) if state_attr else None

            controls_id = el.get_attribute("aria-controls")
            target = page.locator(f"#{controls_id}") if controls_id and page.locator(f"#{controls_id}").count() else None
            target_resting = read_motion_props(target) if target else None
        except Exception:
            continue
        label = element_label(el, i)

        try:
            el.click(timeout=1500)
            page.wait_for_timeout(350)
            if page.url != original_url:
                page.go_back(wait_until="networkidle", timeout=8000)
                continue  # this "toggle" navigated instead — not a result, and already recovered

            toggled = read_motion_props(el)
            after_state = el.get_attribute(state_attr) if state_attr else None
            changes = diff_states(resting, toggled)
            if changes:
                results.append({
                    "element": label, "attribute": state_attr,
                    "stateChange": f"{before_state} -> {after_state}", "changes": changes, "via": "own attribute",
                })

            if target is not None:
                target_changes = diff_states(target_resting, read_motion_props(target))
                if target_changes:
                    results.append({
                        "element": f"{label} -> #{controls_id}", "attribute": "aria-controls target",
                        "stateChange": "closed -> open (inferred from style change)", "changes": target_changes, "via": "aria-controls",
                    })

            el.click(timeout=1500)  # best-effort restore
        except Exception:
            continue

    if page.url != original_url:
        page.goto(original_url, wait_until="networkidle", timeout=15000)
    return results


def capture_disabled_states(page, selector, max_elements):
    """No click needed — a disabled control's style is already sitting in the DOM,
    it's just never been asked for. Read it directly: opacity, cursor, color, and
    whether it's visually distinguishable from its enabled sibling at all (a
    disabled button that looks identical to an enabled one is a real finding,
    not a non-result)."""
    selector = selector or DEFAULT_DISABLED_SELECTOR
    locators = page.locator(selector)
    count = min(locators.count(), max_elements)
    results = []

    for i in range(count):
        el = locators.nth(i)
        try:
            label = element_label(el, i)
            style = el.evaluate(
                """el => { const cs = getComputedStyle(el); return {
                    opacity: cs.opacity, cursor: cs.cursor, color: cs.color,
                    backgroundColor: cs.backgroundColor, pointerEvents: cs.pointerEvents,
                }}"""
            )
            results.append({"element": label, "style": style})
        except Exception:
            continue
    return results


def capture_all_motion(page, selector, scroll_selector, toggle_selector, disabled_selector, max_elements):
    return {
        "pseudoClass": capture_pseudo_class_motion(page, selector, max_elements),
        "scrollReveal": capture_scroll_reveal(page, scroll_selector, max_elements),
        "clickToggle": capture_click_toggles(page, toggle_selector, max_elements),
        "disabled": capture_disabled_states(page, disabled_selector, max_elements),
        "libraries": page.evaluate(LIBRARY_SIGNATURE_JS),
    }


def print_motion_report(report):
    libs = report["libraries"]
    print(f"   Motion library signatures: {', '.join(libs) if libs else 'none detected'}")

    pseudo = report["pseudoClass"]
    if not pseudo:
        print("   Pseudo-class (hover/active/focus): no measurable change on the matched elements.")
    for entry in pseudo:
        if entry["resting"].get("animationTimeline"):
            print(f"   [{entry['element']}] native scroll-driven animation: animation-timeline: {entry['resting']['animationTimeline']}")
        for state in ("hover", "active", "focus"):
            for prop, vals in entry[state].items():
                print(f"   [{entry['element']}] {state} -> {prop}: {vals[prop]}  (resting: {vals['resting']})")

    scroll = report["scrollReveal"]
    if not scroll["results"]:
        note = "no below-the-fold candidates matched --scroll-selector" if not scroll["belowFoldCandidates"] else "no measurable change on scroll-into-view"
        print(f"   Scroll-reveal: {note}.")
    for entry in scroll["results"]:
        for prop, vals in entry["revealed"].items():
            print(f"   [{entry['element']}] scroll-reveal -> {prop}: {vals[prop]}  (before entering viewport: {vals['resting']})")

    toggles = report["clickToggle"]
    if not toggles:
        print("   Click-toggle (aria-expanded/pressed/selected, data-state, dialogs, menus, tabs, aria-controls targets): no measurable change found.")
    for entry in toggles:
        print(f"   [{entry['element']}] click toggled {entry['attribute']} via {entry['via']} ({entry['stateChange']}):")
        for prop, vals in entry["changes"].items():
            print(f"     {prop}: {vals[prop]}  (before click: {vals['resting']})")

    disabled = report.get("disabled", [])
    if not disabled:
        print("   Disabled states: no [disabled]/[aria-disabled] elements found.")
    for entry in disabled:
        s = entry["style"]
        flat = f"opacity {s['opacity']}, cursor {s['cursor']}, color {s['color']}, pointer-events {s['pointerEvents']}"
        print(f"   [{entry['element']}] disabled style: {flat}")


def slugify(text, fallback):
    if not text:
        return fallback
    slug = "".join(c.lower() if c.isalnum() else "-" for c in text).strip("-")
    slug = "-".join(filter(None, slug.split("-")))[:40]
    return slug or fallback


def find_assets(page, out_dir, min_svg_area, min_img_size):
    """The capability that was missing every other time this capture technique ran
    into an inline-SVG illustration: a dedicated sweep that tells the difference
    between an icon and an illustration by viewBox area, and actually extracts the
    big ones to real files — not something to improvise per run."""
    result = page.evaluate(FIND_ASSETS_JS, {"minSvgArea": min_svg_area, "minImgSize": min_img_size})
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    seen_slugs = {}
    for i, svg in enumerate(result["svgs"]):
        slug = slugify(svg["label"], f"illustration-{i + 1}")
        if slug in seen_slugs:
            seen_slugs[slug] += 1
            slug = f"{slug}-{seen_slugs[slug]}"
        else:
            seen_slugs[slug] = 1
        path = out_dir / f"{slug}.svg"
        path.write_text(svg["outerHTML"], encoding="utf-8")
        saved.append({"path": str(path), "area": svg["area"], "label": svg["label"], "selector": svg["selector"]})

    return {
        "svgsFound": result["svgCount"], "svgsSaved": saved,
        "images": result["images"], "bgImages": result["bgImages"],
    }


def print_assets_report(report):
    print(f"   Inline illustrations (SVG, above the icon-size cutoff): {report['svgsFound']} found, saved to disk.")
    for item in report["svgsSaved"]:
        near = f' — near "{item["label"]}"' if item["label"] else ""
        print(f"     {item['path']}  ({item['area']}px² viewBox{near})")
    if not report["svgsSaved"]:
        print("     None above the cutoff — lower --min-svg-area if the page's illustrations are small, or they may be <img>/background-image instead (see below).")

    print(f"   Real <img> assets (excluding small icons): {len(report['images'])} found.")
    for img in report["images"]:
        near = f' — near "{img["label"]}"' if img["label"] else ""
        print(f"     {img['src']}  ({img['naturalWidth']}x{img['naturalHeight']}{near})")

    if report["bgImages"]:
        print(f"   CSS background-image assets: {len(report['bgImages'])} found — these need a manual crop (--selector on the element) or a direct fetch of the URL inside the css value, this sweep only locates them.")
        for bg in report["bgImages"]:
            print(f"     {bg['selector']}  ({bg['width']}x{bg['height']}) {bg['css'][:80]}")


DEFAULT_SCRUB_POINTS = (0.0, 0.07, 0.20, 0.50, 1.0)
CANVAS_MATH_HINTS = (
    "getContext", "requestAnimationFrame", "warpX", "warpY", "warpScale",
    "smoothstep", "drawImage", "putImageData", "createImageData", "shaderSource",
)


def parse_scrub_points(s):
    pts = []
    for raw in s.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            v = float(raw)
        except ValueError:
            raise argparse.ArgumentTypeError(f"Invalid scrub point: {raw!r} (expected float in 0..1)")
        pts.append(max(0.0, min(1.0, v)))
    return tuple(pts) or DEFAULT_SCRUB_POINTS


def _extract_snippet_windows(text, regex, max_windows=6, radius=180):
    """Extract bounded ±radius char windows around regex matches so 1-line minified
    JS chunks never dump 100KB into stdout."""
    windows = []
    last_end = -1
    for m in regex.finditer(text):
        if m.start() < last_end:
            continue
        start = max(0, m.start() - radius)
        end = min(len(text), m.end() + radius)
        last_end = end
        line_no = text.count("\n", 0, m.start()) + 1
        snippet = " ".join(text[start:end].split())
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(text) else ""
        windows.append({"line": line_no, "offset": m.start(), "match": m.group(0), "snippet": f"{prefix}{snippet}{suffix}"})
        if len(windows) >= max_windows:
            break
    return windows


def inspect_canvas_and_bundles(page, base_url, bundles_dir, selector=None, budget=6000):
    """Detects visible <canvas> elements (2D/WebGL), saves inline and external JS
    scripts to disk, and locates the exact chunk + snippet containing the canvas
    selector, getContext, requestAnimationFrame, or spatial warp equations."""
    probe = page.evaluate(CANVAS_PROBE_JS, selector)
    out_dir = Path(bundles_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []
    for item in probe["inlineScripts"]:
        path = out_dir / item["name"]
        path.write_text(item["content"], encoding="utf-8")
        saved_files.append({"file": str(path), "source": "inline <script>", "sizeKb": max(1, len(item["content"]) // 1024)})

    for idx, raw_url in enumerate(probe["scriptUrls"], 1):
        full_url = urljoin(base_url, raw_url)
        parsed = urlparse(full_url)
        base_name = Path(parsed.path).name or f"script-{idx}.js"
        if not base_name.endswith(".js"):
            base_name = f"{base_name}.js"
        safe_name = f"{idx:02d}-{re.sub(r'[^A-Za-z0-9._-]', '_', base_name)[:60]}"
        content = None
        try:
            resp = page.request.get(full_url, timeout=10000)
            if resp.ok:
                content = resp.text()
        except Exception:
            pass
        if content is None:
            try:
                req = urlrequest.Request(full_url, headers={"User-Agent": DEFAULT_USER_AGENT})
                with urlrequest.urlopen(req, timeout=10) as r:
                    charset = r.headers.get_content_charset() or "utf-8"
                    content = r.read().decode(charset, errors="replace")
            except Exception:
                continue
        path = out_dir / safe_name
        path.write_text(content, encoding="utf-8")
        saved_files.append({"file": str(path), "source": full_url, "sizeKb": max(1, len(content) // 1024)})

    # Build targeted search terms from discovered canvas IDs/classes + math keywords
    tokens = list(CANVAS_MATH_HINTS)
    for c in probe["canvases"]:
        if c.get("id"):
            tokens.insert(0, c["id"])
        if c.get("className"):
            for cls in c["className"].split():
                if len(cls) > 2:
                    tokens.insert(0, cls)

    seen_tokens = []
    for t in tokens:
        if t not in seen_tokens:
            seen_tokens.append(t)
    pattern_str = "|".join(re.escape(t) for t in seen_tokens)
    regex = re.compile(pattern_str, re.IGNORECASE)

    bundle_hits = []
    for entry in saved_files:
        text = Path(entry["file"]).read_text(encoding="utf-8", errors="replace")
        windows = _extract_snippet_windows(text, regex, max_windows=5, radius=160)
        if windows:
            bundle_hits.append({
                "file": entry["file"],
                "source": entry["source"],
                "sizeKb": entry["sizeKb"],
                "matches": windows,
            })

    index_path = out_dir / "index.json"
    index_data = {
        "sourceUrl": base_url,
        "canvases": probe["canvases"],
        "bundlesSaved": saved_files,
        "initialHits": bundle_hits,
    }
    index_path.write_text(json.dumps(index_data, indent=2), encoding="utf-8")
    return {
        "canvases": probe["canvases"],
        "bundlesCount": len(saved_files),
        "bundlesDir": str(out_dir),
        "hits": bundle_hits,
        "budget": budget,
    }


def print_canvas_report(report):
    canvases = report["canvases"]
    print(f"   Visible <canvas> elements: {len(canvases)} found; {report['bundlesCount']} JS bundle(s) saved to {report['bundlesDir']}/.")
    for c in canvases:
        near = f' — near "{c["label"]}"' if c.get("label") else ""
        sticky = (
            f" | inside sticky {c['sticky']['stickySelector']} (track {c['sticky']['trackSelector']}, "
            f"runway {c['sticky']['runwayPx']}px)"
            if c.get("sticky") else ""
        )
        print(
            f"     {c['selector']}  (intrinsic {c['attrWidth']}x{c['attrHeight']}, "
            f"CSS {c['cssWidth']}x{c['cssHeight']}{near}{sticky})"
        )

    hits = report["hits"]
    if not hits:
        print("   No canvas/math hits in fetched scripts.")
        return

    used = 0
    budget = report.get("budget", 6000)
    print(f"   JS bundle hits ({len(hits)} file(s) matched canvas selector / getContext / rAF / warp math):")
    for h in hits:
        header = f"     [{h['file']}] ({h['sizeKb']} KB, from {h['source']})"
        if used + len(header) > budget:
            print(f"     (+more matches truncated at --budget {budget}; query with --search-bundles)")
            break
        print(header)
        used += len(header) + 1
        for m in h["matches"]:
            line = f"       L{m['line']}@{m['offset']} ({m['match']}): {m['snippet']}"
            if used + len(line) > budget:
                print(f"       (+more snippets truncated — run: python capture_site.py --search-bundles 'REGEX' --bundles-out {report['bundlesDir']})")
                break
            print(line)
            used += len(line) + 1
    print(f"   Search saved bundles offline without re-fetching:")
    print(f"     python scripts/capture_site.py --search-bundles 'warp|scaleY|getContext' --bundles-out {report['bundlesDir']}")


def search_saved_bundles(bundles_dir, pattern, budget=6000):
    """Offline regex search across saved JS bundles in bundles_dir, returning
    bounded ±180-char windows so minified 1-line bundles remain readable."""
    out_dir = Path(bundles_dir)
    if not out_dir.exists():
        return f"Bundles folder {out_dir} not found. Run capture_site.py <URL> --inspect-canvas first."
    js_files = sorted(out_dir.glob("*.js"))
    if not js_files:
        return f"No .js files found in {out_dir}. Run capture_site.py <URL> --inspect-canvas first."

    regex = re.compile(pattern, re.IGNORECASE)
    lines = [f"# Bundle search /{pattern}/ in {out_dir}/ ({len(js_files)} file(s) scanned)"]
    used = len(lines[0])
    total_matches = 0

    for js_file in js_files:
        text = js_file.read_text(encoding="utf-8", errors="replace")
        windows = _extract_snippet_windows(text, regex, max_windows=12, radius=180)
        if not windows:
            continue
        file_header = f"\n## {js_file.name} ({len(windows)} window(s))"
        if used + len(file_header) > budget:
            lines.append(f"\n(+output capped at --budget {budget} chars; narrow your regex or raise --budget)")
            break
        lines.append(file_header)
        used += len(file_header) + 1
        for w in windows:
            entry = f"- L{w['line']}@{w['offset']} `{w['match']}`: {w['snippet']}"
            if used + len(entry) > budget:
                lines.append(f"- (+more windows capped at --budget {budget})")
                break
            lines.append(entry)
            used += len(entry) + 1
            total_matches += 1

    if total_matches == 0:
        return f"No match for /{pattern}/ across {len(js_files)} bundle file(s) in {out_dir}/."
    return "\n".join(lines)


def capture_scroll_scrub(page, base_path, selector, scrub_points):
    """Scrubs a sticky scroll-pinned container (or tall element/document runway)
    across key progress points (e.g. p=0.00 rest, p=0.07 mid-transition k≈0.35,
    p=0.20 next rest) and samples both viewport screenshots and <canvas>
    center-vs-edge vertical span profiles."""
    info = page.evaluate(SCROLL_SCRUB_LOCATE_JS, selector)
    track_top = info["trackTop"]
    runway = info["runwayPx"]
    canvas_sel = info["canvasSelector"]
    stem, suffix = base_path.stem, base_path.suffix or ".png"

    frames_saved = []
    for idx, p in enumerate(scrub_points, 1):
        target_y = round(track_top + p * runway)
        page.evaluate(f"window.scrollTo(0, {target_y})")
        # Let two rAF ticks + 350ms settle any lerp/spring loop on scroll
        page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
        page.wait_for_timeout(350)

        pct_label = f"{int(round(p * 100)):03d}"
        frame_path = base_path.with_name(f"{stem}-scrub-{idx:02d}-p{pct_label}{suffix}")
        page.screenshot(path=str(frame_path))
        profile = page.evaluate(CANVAS_SLICE_PROFILE_JS, canvas_sel) if canvas_sel else None
        frames_saved.append({
            "progress": p,
            "scrollY": target_y,
            "path": str(frame_path),
            "canvasProfile": profile,
        })

    page.evaluate("window.scrollTo(0, 0)")
    return {"info": info, "frames": frames_saved}


def print_scroll_scrub_report(report):
    info = report["info"]
    sticky_sel = info.get("stickySelector")
    sticky_suffix = f", sticky={sticky_sel}" if sticky_sel else ""
    print(
        f"   Scroll-scrub [{info['mode']}]: track={info['trackSelector']} "
        f"(top={info['trackTop']}px, height={info['trackHeight']}px, runway={info['runwayPx']}px{sticky_suffix})"
    )
    for f in report["frames"]:
        prof = f.get("canvasProfile")
        prof_str = ""
        if prof and prof.get("centerPct"):
            ratio = prof["edgeToCenterRatio"]
            shape = (
                "receding tunnel (shrinks outward)" if ratio is not None and ratio < 0.92
                else ("expanding funnel (grows outward)" if ratio is not None and ratio > 1.08 else "flat / uniform height")
            )
            prof_str = (
                f" | canvas span L={prof['leftPct']}% C={prof['centerPct']}% R={prof['rightPct']}% "
                f"(edge/center={ratio} -> {shape})"
            )
        print(f"     p={f['progress']:.2f} (scrollY={f['scrollY']}px): {f['path']}{prof_str}")


def capture_one(url, output_path, viewport, label, *, save_html, dismiss_cookies, scroll_capture,
                 selector, motion, motion_max, scroll_selector, toggle_selector, disabled_selector,
                 inspect_canvas_flag, bundles_out, budget,
                 scroll_scrub_flag, scrub_points, compare_ref,
                 find_assets_flag, asset_out, min_svg_area, min_img_size,
                 user_agent, wait_until, timeout, full_page, frames, styles):
    from playwright.sync_api import sync_playwright

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Capturing [{label}] {url}  ({viewport[0]}x{viewport[1]}, wait: {wait_until})")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, user_agent=user_agent)
        page = context.new_page()

        try:
            page.goto(url, wait_until=wait_until, timeout=timeout)
        except Exception as e:
            print(f"   Page took longer than expected: {e}. Continuing with what rendered.")
        page.wait_for_timeout(1000)

        if dismiss_cookies:
            dismiss_cookie_banner(page)
        if scroll_capture:
            scroll_through_page(page)

        # Auto-detect whether the target selector (or page) contains a visible <canvas>
        canvas_probe_summary = page.evaluate(CANVAS_PROBE_JS, selector)
        has_visible_canvas = bool(canvas_probe_summary.get("canvases"))

        if inspect_canvas_flag or (selector and has_visible_canvas):
            if not inspect_canvas_flag:
                print("   Selector contains a visible <canvas> — auto-running --inspect-canvas to extract JS math...")
            else:
                print("   Inspecting <canvas> elements and saving loaded JS bundles...")
            print_canvas_report(inspect_canvas_and_bundles(page, url, bundles_out, selector=selector, budget=budget))

        if motion:
            print("   Capturing motion (pseudo-class, scroll-reveal, click-toggle)...")
            print_motion_report(capture_all_motion(page, selector, scroll_selector, toggle_selector, disabled_selector, motion_max))
            if page.url != url:
                print(f"   Motion probing drifted to {page.url} — returning to the target URL before continuing.")
                page.goto(url, wait_until=wait_until, timeout=timeout)
                page.wait_for_timeout(500)

        if scroll_scrub_flag:
            print("   Scrubbing scroll-pinned runway across rest and mid-transition states...")
            print_scroll_scrub_report(capture_scroll_scrub(page, output_path, selector, scrub_points))

        if find_assets_flag:
            print("   Finding illustrations and real images (not icons)...")
            print_assets_report(find_assets(page, asset_out, min_svg_area, min_img_size))

        primary_shot = output_path
        if selector:
            locator = page.locator(selector).first
            try:
                locator.wait_for(state="visible", timeout=10000)
            except Exception:
                browser.close()
                raise RuntimeError(f"Selector matched nothing visible: {selector!r}.")
            locator.scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            locator.screenshot(path=str(output_path))
            print(f"   Element screenshot saved: {output_path}")
            if save_html:
                html_path = output_path.with_suffix(".html")
                html_path.write_text(locator.evaluate("el => el.outerHTML"), encoding="utf-8")
                print(f"   Element outerHTML saved: {html_path}")
        elif full_page or compare_ref:
            page.screenshot(path=str(output_path), full_page=full_page)
            print(f"   Screenshot saved: {output_path}")
        else:
            frame_paths = capture_frames(page, output_path, viewport, frames)
            for frame_path in frame_paths:
                print(f"   Frame saved: {frame_path}")
            if frame_paths:
                primary_shot = frame_paths[0]

        if styles and not selector:
            print("   Computed styles (from the live DOM):")
            for line in page.evaluate(STYLE_PROBE_JS):
                print(f"     {line}")

        # Independent of --styles on purpose: HTML saving and the style digest answer
        # different questions, and coupling them (the original bug) silently dropped
        # the HTML whenever someone passed --no-styles for a quieter run.
        if save_html and not selector:
            html_path = output_path.with_suffix(".html")
            content = page.content()
            html_path.write_text(content, encoding="utf-8")
            print(f"   Rendered HTML saved: {html_path} ({len(content) // 1024} KB; grep it, never read it whole)")

        browser.close()

    if compare_ref:
        from compare_capture import check_pillow, compare_images, print_compare_report
        if not check_pillow():
            sys.exit(2)
        diff_out = output_path.with_name(f"{output_path.stem}-compare-diff.png")
        report = compare_images(Path(compare_ref), Path(primary_shot), diff_out)
        print_compare_report(report)

    return str(output_path)


def main():
    parser = argparse.ArgumentParser(
        description="Capture a website with Playwright.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__,
    )
    parser.add_argument("url", nargs="?", help="URL of the site to capture (optional when using --search-bundles)")
    parser.add_argument("--output", "-o", default="./capture.png")
    parser.add_argument("--viewports", type=parse_viewports_list, default=None)
    parser.add_argument("--frames", type=int, default=4)
    parser.add_argument("--full-page", action="store_true")
    parser.add_argument("--no-styles", dest="styles", action="store_false", default=True)
    parser.add_argument("--save-html", dest="save_html", action="store_true", default=None)
    parser.add_argument("--no-save-html", dest="save_html", action="store_false")
    parser.add_argument("--no-dismiss-cookies", dest="dismiss_cookies", action="store_false", default=True)
    parser.add_argument("--selector", default=None, help="CSS selector; screenshots only that element.")
    parser.add_argument("--scroll-capture", action="store_true")
    parser.add_argument("--motion", action="store_true",
                         help="Capture real motion: forced :hover/:active/:focus, scroll-reveal, and click-toggles.")
    parser.add_argument("--motion-max", type=int, default=12, help="Max elements to probe per motion pass (default: 12).")
    parser.add_argument("--scroll-selector", default=None,
                         help="Elements to test for scroll-reveal motion (default: section/article/common reveal classes).")
    parser.add_argument("--toggle-selector", default=None,
                         help="Elements to click-test for state toggles (default: covers aria-expanded/pressed, "
                              "data-state, dialogs, menus, popovers, tabs, and aria-haspopup/aria-controls triggers).")
    parser.add_argument("--disabled-selector", default=None,
                         help="Elements to read for disabled-state styling, no click needed "
                              "(default: :disabled, [aria-disabled], [data-disabled]).")
    parser.add_argument("--inspect-canvas", action="store_true",
                         help="Detect visible <canvas> elements, save loaded JS bundles to --bundles-out, and print "
                              "a capped digest of where the canvas selector, getContext, rAF, and warp math live.")
    parser.add_argument("--bundles-out", default="./bundles",
                         help="Folder to save and search extracted JS bundles (default: ./bundles).")
    parser.add_argument("--search-bundles", metavar="REGEX", default=None,
                         help="Search saved JS bundles in --bundles-out offline (no browser or network).")
    parser.add_argument("--budget", type=int, default=6000,
                         help="Max characters for bundle digest and --search-bundles output (default: 6000).")
    parser.add_argument("--scroll-scrub", action="store_true",
                         help="Scrub a sticky scroll-pinned section across key progress points (rest p=0.00, "
                              "mid-transition p=0.07, next-rest p=0.20, p=0.50, p=1.00) and measure <canvas> vertical span.")
    parser.add_argument("--scrub-points", type=parse_scrub_points, default=DEFAULT_SCRUB_POINTS,
                         help="Comma-separated progress points in 0..1 for --scroll-scrub (default: 0.0,0.07,0.20,0.50,1.0).")
    parser.add_argument("--compare", metavar="REF_IMAGE", default=None,
                         help="Compare the captured screenshot against REF_IMAGE and produce a 3-panel onion-skin diff + reach report.")
    parser.add_argument("--find-assets", action="store_true",
                         help="Find and extract inline-SVG illustrations and real <img> assets (not icons) — "
                              "run this whenever the page has custom illustrations, which no other pass here sees.")
    parser.add_argument("--asset-out", default="assets", help="Folder to save extracted SVG illustrations into (default: assets).")
    parser.add_argument("--min-svg-area", type=int, default=MIN_SVG_AREA,
                         help=f"Minimum SVG viewBox area (px²) to count as an illustration, not an icon (default: {MIN_SVG_AREA}).")
    parser.add_argument("--min-img-size", type=int, default=MIN_IMG_SIZE,
                         help=f"Minimum <img> width or height (px) to count as a real image, not an icon (default: {MIN_IMG_SIZE}).")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--wait-until", choices=["load", "domcontentloaded", "networkidle"], default="networkidle")
    parser.add_argument("--timeout", type=int, default=30000)
    args = parser.parse_args()

    if args.search_bundles:
        print(search_saved_bundles(args.bundles_out, args.search_bundles, budget=args.budget))
        return

    if not args.url:
        parser.error("a URL is required unless --search-bundles is given")

    if not check_playwright_installed():
        sys.exit(2)

    viewports = args.viewports
    if not viewports and args.compare:
        ref_p = Path(args.compare)
        if not ref_p.exists():
            print(f"Reference image not found: {ref_p}", file=sys.stderr)
            sys.exit(1)
        try:
            from PIL import Image
            with Image.open(ref_p) as im:
                viewports = [("ref-match", im.size)]
        except Exception:
            viewports = [("desktop", VIEWPORT_PRESETS["desktop"])]
    elif not viewports:
        viewports = [("desktop", VIEWPORT_PRESETS["desktop"])]

    base_path = Path(args.output)
    total = len(viewports)

    try:
        for label, viewport in viewports:
            out = base_path if total == 1 else base_path.with_name(f"{base_path.stem}-{label}{base_path.suffix or '.png'}")
            capture_one(
                url=args.url, output_path=out, viewport=viewport, label=label,
                save_html=args.save_html if args.save_html is not None else bool(args.selector),
                dismiss_cookies=args.dismiss_cookies, scroll_capture=args.scroll_capture,
                selector=args.selector, motion=args.motion, motion_max=args.motion_max,
                scroll_selector=args.scroll_selector, toggle_selector=args.toggle_selector, disabled_selector=args.disabled_selector,
                inspect_canvas_flag=args.inspect_canvas, bundles_out=args.bundles_out, budget=args.budget,
                scroll_scrub_flag=args.scroll_scrub, scrub_points=args.scrub_points, compare_ref=args.compare,
                find_assets_flag=args.find_assets, asset_out=args.asset_out,
                min_svg_area=args.min_svg_area, min_img_size=args.min_img_size,
                user_agent=args.user_agent, wait_until=args.wait_until, timeout=args.timeout,
                full_page=args.full_page, frames=args.frames, styles=args.styles,
            )
    except Exception as e:
        print(f"Error during capture: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

