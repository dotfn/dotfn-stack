// dotfn-audit checks — self-contained. Paste into any evaluate() call (a
// browser console, Claude in Chrome, Chrome DevTools MCP, Puppeteer/Playwright
// page.evaluate) and it runs with zero setup. Returns the report as an object
// and also leaves it at window.__dotfnAudit.
//
// Options (all optional), set before evaluating:
//   window.DOTFN_AUDIT = { minText: 14, spacing: [4,8,12,16,24,32,48,64], measure: [45,80] };
//
// What this script CANNOT check without a driven browser (Playwright, etc.):
// real keyboard focus, forced hover/focus state, reduced-motion behavior,
// and console errors. Those are listed in `notMeasured`, never silently
// reported as zero.
(() => {
  const DEV_OVERLAYS = 'nextjs-portal,vite-error-overlay,astro-dev-toolbar,[data-nextjs-toast]';
  const DISABLED = ':disabled,[aria-disabled="true"]';

  // --- shared helpers -------------------------------------------------

  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 1;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });

  const paint = (layers) => {
    ctx.clearRect(0, 0, 1, 1);
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, 1, 1);
    for (const color of layers) {
      ctx.fillStyle = color;
      ctx.fillRect(0, 0, 1, 1);
    }
    return [...ctx.getImageData(0, 0, 1, 1).data.slice(0, 3)];
  };

  const alphaOf = (color) => {
    ctx.clearRect(0, 0, 1, 1);
    ctx.fillStyle = color;
    ctx.fillRect(0, 0, 1, 1);
    return ctx.getImageData(0, 0, 1, 1).data[3] / 255;
  };

  const relativeLuminance = (rgb) =>
    rgb
      .map((c) => c / 255)
      .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
      .reduce((sum, c, i) => sum + c * [0.2126, 0.7152, 0.0722][i], 0);

  const contrastRatio = (a, b) => {
    const [hi, lo] = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
  };

  const isVisible = (el) => {
    const rect = el.getBoundingClientRect();
    if (!rect.width || !rect.height) return false;
    for (let n = el; n; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (cs.display === 'none' || cs.visibility === 'hidden' || Number(cs.opacity) === 0) return false;
    }
    return true;
  };

  const elementOpacity = (el) => {
    let product = 1;
    for (let n = el; n; n = n.parentElement) product *= Number(getComputedStyle(n).opacity);
    return product;
  };

  const backgroundBehind = (el) => {
    const layers = [];
    let overImage = false;
    for (let n = el; n; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (cs.backgroundImage !== 'none') overImage = true;
      layers.unshift(cs.backgroundColor);
    }
    return { rgb: paint(layers), overImage };
  };

  const labelOf = (el) =>
    (el.textContent || el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.tagName)
      .trim().replace(/\s+/g, ' ').slice(0, 32);

  const activeElements = (selector) =>
    [...document.querySelectorAll(selector)].filter(
      (el) => !el.closest(`[inert],[aria-hidden="true"],${DEV_OVERLAYS}`) && isVisible(el),
    );

  // --- checks -----------------------------------------------------------

  const checkTextContrastAndSize = (minText) => {
    const lowContrast = [];
    const borderline = [];
    const smallText = [];
    let overImageCount = 0;
    let totalTextElements = 0;

    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const seen = new Set();
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const el = node.parentElement;
      if (!node.textContent.trim() || !el || ['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(el.tagName)) continue;
      if (el.closest(`[aria-hidden="true"],${DEV_OVERLAYS},${DISABLED}`) || !isVisible(el) || seen.has(el)) continue;
      seen.add(el);
      totalTextElements++;

      const cs = getComputedStyle(el);
      const px = parseFloat(cs.fontSize);
      if (px < minText) smallText.push({ text: labelOf(el), px });

      const bg = backgroundBehind(el);
      if (bg.overImage) {
        overImageCount++;
        continue;
      }
      const inkWithOpacity = paint([`rgb(${bg.rgb.join(',')})`, `rgba(${paint([`rgb(${bg.rgb.join(',')})`, cs.color]).join(',')},${elementOpacity(el)})`]);
      const ratio = contrastRatio(inkWithOpacity, bg.rgb);
      const weight = Number(cs.fontWeight) || 400;
      const isLargeText = px >= 24 || (px >= 18.66 && weight >= 700);
      const minimum = isLargeText ? 3 : 4.5;
      const item = { text: labelOf(el), px, ratio: +ratio.toFixed(2), min: minimum };
      if (ratio < minimum) lowContrast.push(item);
      else if (ratio < minimum + 0.5) borderline.push(item);
    }

    return { lowContrast, borderline, smallText, overImageCount, totalTextElements };
  };

  const checkHitTargets = (touch) => {
    const minSize = touch ? 44 : 24;
    return activeElements('a[href],button,input:not([type=hidden]),select,textarea,[role=button],[role=tab],[role=switch]')
      .filter((el) => {
        const rect = el.getBoundingClientRect();
        if (Math.min(rect.width, rect.height) >= minSize) return false;
        const label = el.closest('label');
        if (label) {
          const labelRect = label.getBoundingClientRect();
          if (Math.min(labelRect.width, labelRect.height) >= minSize) return false;
        }
        return !(el.tagName === 'A' && getComputedStyle(el).display === 'inline' && el.closest('p,li'));
      })
      .map((el) => {
        const rect = el.getBoundingClientRect();
        return { text: labelOf(el), w: Math.round(rect.width), h: Math.round(rect.height) };
      });
  };

  const checkControlContrast = () => {
    const low = [];
    let measured = 0, textOnly = 0, native = 0;
    const borderColorOf = (cs) => {
      for (const side of ['Top', 'Right', 'Bottom', 'Left']) {
        if (cs[`border${side}Style`] !== 'none' && parseFloat(cs[`border${side}Width`]) >= 1 && alphaOf(cs[`border${side}Color`]) > 0.05) {
          return cs[`border${side}Color`];
        }
      }
      return null;
    };

    for (const el of activeElements('button,input:not([type=hidden]),select,textarea,[role=button],[role=switch],[role=checkbox]')) {
      if (el.closest(DISABLED)) continue;
      const cs = getComputedStyle(el);
      if (el.matches('input[type=checkbox],input[type=radio]') && cs.appearance !== 'none') {
        native++;
        continue;
      }
      const isField = el.matches('input,select,textarea,[role=switch],[role=checkbox]');
      if (!isField && el.textContent.trim()) {
        textOnly++;
        continue;
      }
      const around = backgroundBehind(el.parentElement || document.body);
      if (around.overImage) continue;

      const border = borderColorOf(cs);
      const fill = alphaOf(cs.backgroundColor) > 0.05 ? cs.backgroundColor : null;
      measured++;
      const base = `rgb(${around.rgb.join(',')})`;
      const best = Math.max(
        border ? contrastRatio(paint([base, border]), around.rgb) : 1,
        fill ? contrastRatio(paint([base, fill]), around.rgb) : 1,
      );
      if (best < 3) low.push({ text: labelOf(el), ratio: +best.toFixed(2), min: 3, why: !border && !fill ? 'no visible boundary' : undefined });
    }
    return { low, measured, textOnly, native };
  };

  const checkSpacingScale = (allowedScale) => {
    const uses = new Map();
    let total = 0;
    const props = ['marginTop', 'marginRight', 'marginBottom', 'marginLeft',
                    'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'rowGap', 'columnGap'];
    const onScale = (v) => (allowedScale ? allowedScale.some((s) => Math.abs(s - v) < 0.5) : Math.abs(v - 4 * Math.round(v / 4)) < 0.5);

    for (const el of document.querySelectorAll('body *')) {
      if (el.closest('[data-spacing-ok],svg') || !isVisible(el)) continue;
      const cs = getComputedStyle(el);
      for (const prop of props) {
        const raw = cs[prop];
        if (!raw || raw === 'normal' || raw === 'auto') continue;
        const value = Math.abs(parseFloat(raw));
        if (!value || value <= 1) continue;
        total++;
        const key = Math.round(value * 10) / 10;
        uses.set(key, (uses.get(key) || 0) + 1);
      }
    }
    const off = [...uses].filter(([v]) => !onScale(v)).sort((a, b) => b[1] - a[1]).map(([value, count]) => ({ value, count }));
    return { off, distinctValues: uses.size, totalUses: total, scale: allowedScale ?? 'multiples of 4' };
  };

  const checkLineLength = (min, max) => {
    const long = [], short = [];
    let blocks = 0;
    for (const el of document.querySelectorAll('p,li')) {
      if (!isVisible(el) || el.querySelector('p,li,ul,ol,button,[role=button]') || el.closest('button,[role=button],nav')) continue;
      const text = el.textContent.replace(/\s+/g, ' ').trim();
      if (text.length < 40) continue;
      const range = document.createRange();
      range.selectNodeContents(el);
      const lines = new Set([...range.getClientRects()].filter((r) => r.width > 1).map((r) => Math.round(r.top / 4))).size;
      if (lines <= 2) continue;
      blocks++;
      const charsPerLine = Math.round(text.length / lines);
      const item = { text: labelOf(el), charsPerLine, lines };
      if (charsPerLine > max) long.push(item);
      else if (charsPerLine < min) short.push(item);
    }
    return { long, short, blocks, min, max };
  };

  const checkHeadingBalance = () =>
    activeElements('h1,h2,h3')
      .filter((h) => !`${getComputedStyle(h).textWrap || ''}`.match(/balance|pretty/))
      .map(labelOf);

  const checkOverflow = () => {
    const viewportWidth = document.documentElement.clientWidth;
    const roots = [];
    for (const el of document.querySelectorAll('body *')) {
      const rect = el.getBoundingClientRect();
      if (!rect.width || rect.right <= viewportWidth + 1 || getComputedStyle(el).position === 'fixed') continue;
      if (el.closest('[data-overflow-ok]') || roots.some((r) => r.contains(el))) continue;
      let clipped = false;
      for (let n = el.parentElement; n && n !== document.body; n = n.parentElement) {
        if (getComputedStyle(n).overflowX !== 'visible') { clipped = true; break; }
      }
      if (!clipped) roots.push(el);
    }
    return roots.slice(0, 10).map((el) => `${el.tagName.toLowerCase()}${el.className ? '.' + String(el.className).split(' ')[0] : ''}`);
  };

  const checkZoomLocked = () => {
    const meta = document.querySelector('meta[name="viewport"]')?.content || '';
    return /maximum-scale\s*=\s*1(\.0)?\b|user-scalable\s*=\s*(no|0)/.test(meta);
  };

  // --- run ----------------------------------------------------------

  const opts = Object.assign({}, window.DOTFN_AUDIT || {});
  const minText = Number(opts.minText ?? 14);
  const spacing = opts.spacing ? [...opts.spacing].map(Number) : null;
  const [measureMin, measureMax] = opts.measure ?? [45, 80];
  const touch = opts.touch ?? (matchMedia('(pointer: coarse)').matches || document.documentElement.clientWidth < 1024);

  const textCheck = checkTextContrastAndSize(minText);
  const controlContrast = checkControlContrast();
  const smallTargets = checkHitTargets(touch);
  const spacingScale = checkSpacingScale(spacing);
  const lineLength = checkLineLength(measureMin, measureMax);
  const unbalancedHeadings = checkHeadingBalance();
  const overflowing = checkOverflow();
  const zoomLocked = checkZoomLocked();
  const scrollX = document.documentElement.scrollWidth > document.documentElement.clientWidth + 1;

  const hard = [
    scrollX && 'horizontal scroll',
    zoomLocked && 'zoom locked',
    textCheck.lowContrast.length && `${textCheck.lowContrast.length} low text contrast`,
    controlContrast.low.length && `${controlContrast.low.length} low control contrast`,
  ].filter(Boolean);

  const result = {
    url: location.href,
    viewport: `${document.documentElement.clientWidth}x${document.documentElement.clientHeight}`,
    minText,
    touch,
    hard,
    lowContrast: textCheck.lowContrast,
    borderlineContrast: textCheck.borderline,
    smallText: textCheck.smallText,
    textsChecked: textCheck.totalTextElements,
    textsOverImage: textCheck.overImageCount,
    controlContrast,
    smallTargets,
    spacingScale,
    lineLength,
    unbalancedHeadings,
    overflowing,
    zoomLocked,
    scrollX,
    notMeasured: [
      'keyboardFocus: needs real Tab presses to compare the focused and resting state',
      'stateContrast: needs forced hover/focus on each control',
      'reducedMotion: needs a reload with prefers-reduced-motion: reduce',
      'consoleErrors: needs to listen from page load',
      'screenshots and other viewports/routes: need a driven browser',
    ],
  };

  window.__dotfnAudit = result;
  return result;
})();
