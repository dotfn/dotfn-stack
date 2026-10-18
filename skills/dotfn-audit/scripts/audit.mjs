#!/usr/bin/env node
// dotfn-audit driver — optional. Adds what checks.js cannot do without a
// real, driven browser: a real keyboard focus walk, forced hover/focus state
// contrast, a reduced-motion reload, console/network error capture,
// screenshots, multi-route/multi-viewport looping, and a CI-friendly exit
// code. Needs `playwright` or `playwright-core` in the *target* project.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const args = process.argv.slice(2);
const flag = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i === -1 ? fallback : args[i + 1];
};
const has = (name) => args.includes(`--${name}`);

if (has('help')) {
  console.log(`dotfn-audit

  node audit.mjs [--url http://localhost:3000] [--routes /,/pricing] [--viewports 390x844,1440x900]
                 [--min-text 14] [--spacing 4,8,12,16,24,32,48,64] [--measure 45,80]
                 [--states-max 40] [--out audit] [--config dotfn-audit.json] [--json] [--verbose]

Without --url, looks for a dev server on 3000, 3001, 3002, 4321, 5173, 8080.`);
  process.exit(0);
}

const configPath = flag('config', 'dotfn-audit.json');
const config = existsSync(configPath) ? JSON.parse(readFileSync(configPath, 'utf8')) : {};

const list = (v) => (Array.isArray(v) ? v : String(v).split(',')).map((s) => String(s).trim()).filter(Boolean);
const parseViewport = (v) => {
  const [width, height] = (typeof v === 'object' ? [v.width, v.height] : v.split('x').map(Number));
  return { width: Number(width), height: Number(height) };
};

const findDevServer = async () => {
  for (const port of [3000, 3001, 3002, 4321, 5173, 8080]) {
    try {
      const res = await fetch(`http://localhost:${port}/`, { signal: AbortSignal.timeout(1500) });
      if (res.status < 500) return `http://localhost:${port}`;
    } catch {
      /* try the next port */
    }
  }
  console.error('No dev server found on 3000, 3001, 3002, 4321, 5173, or 8080. Start it, or pass --url.');
  process.exit(2);
};

const baseUrl = (flag('url') ?? config.url ?? (await findDevServer())).replace(/\/$/, '');
const routes = list(flag('routes') ?? config.routes ?? ['/']).map((r) => (r.startsWith('/') ? r : `/${r === 'home' ? '' : r}`));
const viewports = list(flag('viewports') ?? config.viewports ?? ['390x844']).map(parseViewport);
const minText = Number(flag('min-text') ?? config.minText ?? 14);
const spacingRaw = flag('spacing') ?? config.spacing;
const spacing = spacingRaw ? list(spacingRaw).map(Number) : null;
const [measureMin, measureMax] = list(flag('measure') ?? config.measure ?? '45,80').map(Number);
const statesMax = Number(flag('states-max') ?? config.statesMax ?? 40);
const outDir = flag('out') ?? config.out ?? 'audit';
const asJson = has('json');
const verbose = has('verbose');

const loadPlaywright = async () => {
  const requireFromProject = createRequire(path.join(process.cwd(), 'package.json'));
  for (const pkg of ['playwright', 'playwright-core']) {
    for (const resolveAs of [() => pathToFileURL(requireFromProject.resolve(pkg)).href, () => pkg]) {
      try {
        const mod = await import(resolveAs());
        const chromium = mod.chromium ?? mod.default?.chromium;
        if (chromium) return chromium;
      } catch {
        /* try the next resolution strategy */
      }
    }
  }
  console.error('Playwright is missing in this project. Run: npm i -D playwright-core');
  process.exit(2);
};

const chromium = await loadPlaywright();
const browser = await chromium.launch({ channel: 'chrome' }).catch(() =>
  chromium.launch().catch(() => {
    console.error('No browser found. Install Chrome, or run: npx playwright install chromium');
    process.exit(2);
  }),
);
mkdirSync(outDir, { recursive: true });

const checksSource = readFileSync(new URL('./checks.js', import.meta.url), 'utf8');
const DEV_OVERLAYS = 'nextjs-portal,vite-error-overlay,astro-dev-toolbar,[data-nextjs-toast]';
const slugify = (route) => (route === '/' ? 'home' : route.replace(/^\/|\/$/g, '').replace(/[^\w-]+/g, '-'));

// --- real keyboard focus walk: press Tab, compare focused vs. resting state ---
const walkKeyboardFocus = async (page) => {
  const missing = [];
  const seen = new Set();
  let walked = 0;
  const freeze = await page.addStyleTag({ content: '*,*::before,*::after{transition:none!important;animation:none!important}' });

  for (let i = 0; i < 40; i++) {
    await page.keyboard.press('Tab');
    const result = await page.evaluate((overlays) => {
      const el = document.activeElement;
      if (!el || el === document.body || el === document.documentElement) return null;
      if (el.closest(overlays)) return { id: el.outerHTML.slice(0, 120), devOverlay: true };

      const chain = [];
      for (let n = el, depth = 0; n && depth < 3; depth++, n = n.parentElement) chain.push(n);
      const readLooks = () =>
        chain.map((n) => {
          const cs = getComputedStyle(n);
          return { hasOutline: cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0, look: `${cs.boxShadow}|${cs.backgroundColor}|${cs.borderColor}` };
        });

      const focusedLook = readLooks();
      el.blur();
      const restingLook = readLooks();
      el.focus();

      let ok = el.matches('input:not([type=checkbox]):not([type=radio]):not([type=range]),textarea,[contenteditable]');
      if (!ok) ok = focusedLook.some((f, i) => f.hasOutline || f.look !== restingLook[i].look);

      return { id: el.outerHTML.slice(0, 120), text: (el.textContent || el.getAttribute('aria-label') || el.tagName).trim().slice(0, 32), ok };
    }, DEV_OVERLAYS);

    if (!result || seen.has(result.id)) break;
    seen.add(result.id);
    if (result.devOverlay) continue;
    walked++;
    if (!result.ok) missing.push(result.text);
  }
  await freeze.evaluate((el) => el.remove());
  return { walked, missing };
};

// --- forced hover/focus state contrast: force the state, read the computed colors ---
const measureForcedState = ({ index, state }) => {
  const el = document.querySelector(`[data-dotfn-i="${index}"]`);
  if (!el) return null;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 1;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  const paint = (layers) => {
    ctx.clearRect(0, 0, 1, 1);
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, 1, 1);
    for (const c of layers) { ctx.fillStyle = c; ctx.fillRect(0, 0, 1, 1); }
    return [...ctx.getImageData(0, 0, 1, 1).data.slice(0, 3)];
  };
  const luminance = (rgb) => rgb.map((c) => c / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
    .reduce((a, c, i) => a + c * [0.2126, 0.7152, 0.0722][i], 0);
  const ratio = (a, b) => { const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  const behind = (node) => {
    const layers = [];
    for (let n = node; n; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (cs.backgroundImage !== 'none') return null;
      layers.unshift(cs.backgroundColor);
    }
    return paint(layers);
  };
  const text = (el.textContent || el.getAttribute('aria-label') || el.tagName).trim().replace(/\s+/g, ' ').slice(0, 32);
  const out = [];
  const cs = getComputedStyle(el);
  const bg = behind(el);
  if (bg && el.textContent.trim()) {
    const px = parseFloat(cs.fontSize);
    const isLarge = px >= 24 || (px >= 18.66 && (Number(cs.fontWeight) || 400) >= 700);
    const minimum = isLarge ? 3 : 4.5;
    const ink = paint([`rgb(${bg.join(',')})`, cs.color]);
    const r = ratio(paint([`rgb(${bg.join(',')})`, `rgb(${ink.join(',')})`]), bg);
    if (r < minimum) out.push({ text, state, part: 'text', ratio: +r.toFixed(2), min: minimum });
  }
  if (state === 'focus' && cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0) {
    const around = behind(el.parentElement || document.body);
    if (around) {
      const r = ratio(paint([`rgb(${around.join(',')})`, cs.outlineColor]), around);
      if (r < 3) out.push({ text, state, part: 'focus ring', ratio: +r.toFixed(2), min: 3 });
    }
  }
  return out;
};

const walkForcedStates = async (page, max) => {
  const total = await page.evaluate(({ max, overlays }) => {
    const ok = (el) => {
      if (el.closest(`[inert],[aria-hidden="true"],:disabled,[aria-disabled="true"],${overlays}`)) return false;
      const rect = el.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    };
    const els = [...document.querySelectorAll('button,a[href],input:not([type=hidden]),select,textarea,[role=button],[role=switch]')]
      .filter(ok).slice(0, max);
    els.forEach((el, i) => el.setAttribute('data-dotfn-i', i));
    return els.length;
  }, { max, overlays: DEV_OVERLAYS });

  const low = [];
  let measured = 0;
  const freeze = await page.addStyleTag({ content: '*,*::before,*::after{transition:none!important;animation:none!important}' });

  for (let i = 0; i < total; i++) {
    const selector = `[data-dotfn-i="${i}"]`;
    for (const state of ['hover', 'focus']) {
      try {
        if (state === 'hover') await page.hover(selector, { timeout: 1200 });
        else {
          await page.mouse.move(0, 0);
          await page.focus(selector, { timeout: 1200 });
        }
      } catch {
        continue;
      }
      await page.waitForTimeout(140);
      const result = await page.evaluate(measureForcedState, { index: i, state });
      if (!result) continue;
      measured++;
      low.push(...result);
    }
    await page.mouse.move(0, 0);
    await page.evaluate(() => document.activeElement?.blur?.());
  }
  await freeze.evaluate((el) => el.remove());
  return { low, measured, controls: total };
};

const countStillAnimating = (page) =>
  page.evaluate((overlays) =>
    [...document.querySelectorAll('body *')].filter((el) => {
      if (el.closest(overlays)) return false;
      const cs = getComputedStyle(el);
      const transitionMax = Math.max(...cs.transitionDuration.split(',').map(parseFloat));
      const hasAnimation = cs.animationName !== 'none' && Math.max(...cs.animationDuration.split(',').map(parseFloat)) > 0.05;
      return transitionMax > 0.05 || hasAnimation;
    }).length, DEV_OVERLAYS);

// --- main loop ------------------------------------------------------

const report = [];
const errors = [];
let anyHardFault = false;

for (const viewport of viewports) {
  const isTouch = viewport.width < 1024;
  const context = await browser.newContext({ viewport, deviceScaleFactor: 2, hasTouch: isTouch, isMobile: isTouch });
  const page = await context.newPage();
  page.on('pageerror', (e) => errors.push(`${page.url()} pageerror: ${e.message}`));
  page.on('console', (m) => m.type() === 'error' && !m.text().startsWith('Failed to load resource') && errors.push(`${page.url()} console: ${m.text()}`));
  page.on('response', (r) => r.status() >= 400 && !r.url().endsWith('/favicon.ico') && errors.push(`HTTP ${r.status()} ${r.url()}`));

  for (const route of routes) {
    const name = `${slugify(route)}-${viewport.width}`;
    const response = await page.goto(baseUrl + route, { waitUntil: 'networkidle' }).catch((e) => ({ error: e.message }));
    if (response?.error || (response && response.status() >= 400)) {
      report.push({ route, viewport: `${viewport.width}x${viewport.height}`, error: response.error?.split('\n')[0] ?? `HTTP ${response.status()}` });
      anyHardFault = true;
      continue;
    }

    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(300);
    const screenshotPath = path.join(outDir, `${name}.png`);
    await page.screenshot({ path: screenshotPath });

    await page.evaluate((o) => (window.DOTFN_AUDIT = o), { minText, spacing, measure: [measureMin, measureMax], touch: isTouch });
    const { hard: _staticHard, notMeasured: _notMeasured, url: _url, viewport: _vp, minText: _mt, touch: _t, ...checked } = await page.evaluate(checksSource);

    const focus = await walkKeyboardFocus(page);
    const states = await walkForcedStates(page, statesMax);

    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.reload({ waitUntil: 'networkidle' });
    const stillAnimatingUnderReducedMotion = await countStillAnimating(page);
    await page.emulateMedia({ reducedMotion: null });

    const hard = [
      checked.scrollX && 'horizontal scroll',
      checked.zoomLocked && 'zoom locked',
      checked.lowContrast.length && `${checked.lowContrast.length} low text contrast`,
      checked.controlContrast.low.length && `${checked.controlContrast.low.length} low control contrast`,
      states.low.length && `${states.low.length} low state contrast`,
    ].filter(Boolean);
    if (hard.length) anyHardFault = true;

    report.push({ route, viewport: `${viewport.width}x${viewport.height}`, screenshot: screenshotPath, hard, ...checked, stateContrast: states, focus, stillAnimatingUnderReducedMotion });
  }
  await context.close();
}
await browser.close();

writeFileSync(path.join(outDir, 'report.json'), JSON.stringify({ baseUrl, minText, report, errors }, null, 2));

if (asJson) {
  console.log(JSON.stringify({ baseUrl, report, errors }, null, 2));
} else {
  const showCounts = (label, items) => {
    const counts = new Map();
    for (const item of items) {
      const key = typeof item === 'string' ? item : JSON.stringify(item);
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    for (const [key, n] of counts) console.log(`    ${label.padEnd(12)} ${key}${n > 1 ? `  x${n}` : ''}`);
  };

  console.log(`dotfn-audit  ${baseUrl}  min text ${minText}px\n`);
  for (const r of report) {
    const head = `${r.route} @ ${r.viewport}`;
    if (r.error) {
      console.log(`${head}\n    ERROR ${r.error}\n`);
      continue;
    }
    console.log(head + (r.hard.length ? `   FAIL: ${r.hard.join(', ')}` : '   ok'));
    console.log([
      `contrast: ${r.lowContrast.length} low, ${r.borderlineContrast.length} borderline of ${r.textsChecked - r.textsOverImage} texts${r.textsOverImage ? ` (${r.textsOverImage} over images, not measured)` : ''}`,
      `text under ${minText}px: ${r.smallText.length}`,
      `small targets: ${r.smallTargets.length}`,
      `focus missing: ${new Set(r.focus.missing).size} of ${r.focus.walked} walked`,
      `still animating under reduced motion: ${r.stillAnimatingUnderReducedMotion}`,
      `unbalanced headings: ${r.unbalancedHeadings.length}`,
      `control contrast: ${r.controlContrast.low.length} low of ${r.controlContrast.measured} (${r.controlContrast.textOnly} text-only and ${r.controlContrast.native} native, not required)`,
      `state contrast: ${r.stateContrast.low.length} low of ${r.stateContrast.measured} states on ${r.stateContrast.controls} controls`,
      `spacing off scale: ${r.spacingScale.off.length} of ${r.spacingScale.distinctValues} distinct values`,
      `line length: ${r.lineLength.long.length} over ${r.lineLength.max}, ${r.lineLength.short.length} under ${r.lineLength.min} of ${r.lineLength.blocks} blocks`,
      r.overflowing.length ? `overflowing: ${r.overflowing.length}` : null,
    ].filter(Boolean).map((s) => '  ' + s).join('\n'));

    showCounts('low', r.lowContrast);
    if (verbose) showCounts('borderline', r.borderlineContrast);
    showCounts('small text', r.smallText);
    showCounts('target', r.smallTargets);
    showCounts('no focus', r.focus.missing);
    showCounts('control', r.controlContrast.low);
    showCounts('state', r.stateContrast.low);
    if (r.spacingScale.off.length) console.log(`    spacing      ${r.spacingScale.off.slice(0, 12).map((o) => `${o.value}px x${o.count}`).join(', ')}`);
    console.log(`    screenshot   ${r.screenshot}\n`);
  }
  console.log(errors.length ? `console/network errors: ${errors.length}` : 'console/network errors: 0');
  showCounts('error', errors);
  if (!report.some((r) => !r.error && r.focus.walked)) {
    console.log('\nNo element received focus on any route — the focus check did not look at anything.');
  }
}

process.exit(anyHardFault ? 1 : 0);
