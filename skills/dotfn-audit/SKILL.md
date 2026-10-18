---
name: dotfn-audit
description: Measure rendered screens in a real browser before anyone looks at them — contrast on the actually-painted color, hit-target size, spacing-scale conformance, line length, keyboard focus, forced hover/focus state contrast, reduced motion, overflow, and zoom-lock, with a screenshot per screen and an exit code for CI. Works with any browser tool that can evaluate JavaScript, and goes deeper with Playwright installed. Use after any change to a web interface and before calling it done.
---

# dotfn audit

What can be measured doesn't get asked as an opinion. The measurement logic lives in `scripts/checks.js`, a self-contained script with no dependencies, so this works with whatever browser tool is already available.

## Tier 1 — any browser tool, no setup

Open the page at the real viewport, wait for fonts to load, then evaluate the contents of `scripts/checks.js` on the page — browser console, Claude in Chrome, Chrome DevTools MCP, Puppeteer, or any `evaluate()` call. The script is a single expression: the call returns the full report as an object, and it's also left at `window.__dotfnAudit` for a follow-up read.

Options are optional; set them before evaluating:

```js
window.DOTFN_AUDIT = { minText: 14, spacing: [4, 8, 12, 16, 24, 32, 48, 64], measure: [45, 80] };
```

The report's `hard` array lists what fails WCAG AA or breaks the page outright. Its `notMeasured` array names exactly what this tier can't check — keyboard focus, forced hover/focus state, reduced motion, console errors — so those get reported as "not checked," never silently folded into a zero.

## Tier 2 — with Playwright in the target project

```bash
npm i -D playwright-core
npx playwright install chromium   # only if no system Chrome is found
node <skill-dir>/scripts/audit.mjs --routes /,/pricing,/settings --viewports 390x844,1440x900
```

Injects the same `checks.js` and adds everything that needs a driven browser: a real `Tab`-key focus walk comparing the focused state against resting, forced `:hover`/`:focus` on each control with the resulting text/outline contrast measured, a reload under `prefers-reduced-motion: reduce` to catch anything still moving that shouldn't be, console and network error capture, looping across every route and viewport, and a screenshot saved per screen.

| Option | Default | Meaning |
|:--|:--|:--|
| `--url` | first dev server found on 3000/3001/3002/4321/5173/8080 | Base URL — pass it whenever more than one server is running |
| `--routes` | `/` | Comma-separated paths |
| `--viewports` | `390x844` | Comma-separated `WIDTHxHEIGHT`; under 1024 wide counts as touch |
| `--min-text` | `14` | Smallest allowed text size, in px |
| `--spacing` | multiples of 4 | Allowed margin/padding/gap values, in px |
| `--measure` | `45,80` | Allowed characters-per-line range for running text |
| `--states-max` | `40` | How many controls get hovered and focused |
| `--out` | `audit` | Folder for screenshots and `report.json` |
| `--config` | `dotfn-audit.json` | Config file to read these from; flags win over it |
| `--json` | off | Print the full report as JSON |
| `--verbose` | off | List borderline (near-miss) contrast one by one |

Exit code is `1` when any hard fault exists (contrast below WCAG AA, a route that fails to load, horizontal scroll, zoom locked), `0` otherwise — gate a commit or a CI step on it directly.

## What it measures, and why it's measured this way

- **Contrast on the color as actually painted.** Every background layer up the ancestor chain plus the text's own color and opacity get painted onto a 1×1 canvas and read back as real pixels. Parsing the computed-style string directly breaks on `oklab()`, `color-mix()`, and alpha — this avoids that failure mode entirely. Text sitting over an image is counted and reported separately, never guessed at.
- **Borderline contrast** — passing by less than 0.5 — is tracked apart from a clean pass. Two shades of the same hue that barely clear the bar still read as a mistake to the eye.
- **Keyboard focus**, by actually pressing `Tab` and comparing the focused element against its own resting state (outline, or a changed box-shadow/background/border on itself or up to two ancestors). A text field passes on its caret alone. The report states how many elements were actually walked — zero faults over zero elements walked means nothing was checked, not that nothing is wrong.
- **Hit targets** at 44px on touch viewports, 24px with a pointer, counting a wrapping `<label>` as the real target. Inline links inside a paragraph are exempt — that's a different, accepted interaction pattern.
- **Control contrast** (WCAG 1.4.11): fields, switches, and icon-only buttons need 3:1 on their border or fill against what's behind them. A button named by its own visible text is exempt — WCAG doesn't require a boundary there, only the text contrast already checked above.
- **State contrast**: each control gets hovered, then focused, with transitions frozen so the measurement lands on the settled state, not a mid-animation frame. Text must hold its minimum contrast in both states, and a focus outline needs 3:1 against what's around it.
- **Spacing scale**: every margin, padding, and gap gets collected; anything off the declared (or default multiples-of-4) scale is reported with how often it recurs. `margin: auto` used for centering or flex alignment is excluded — it isn't really spacing.
- **Line length**: any paragraph or list item spanning more than two lines reports its characters-per-line against the allowed range. Cards and nav items are excluded.
- **Reduced motion**: a full reload under `prefers-reduced-motion: reduce`, then a count of elements still transitioning or animating — that count should be at or near zero.
- **Headings without `text-wrap: balance`/`pretty`**, **overflow** past the viewport width (content correctly scrolling inside its own container doesn't count), and a **zoom-locked** viewport meta tag.

## Reading the result

- Ignore dev-server overlays (Next.js, Vite, Astro) — they're already filtered out. Still, audit a production build when one is available; a dev overlay can mask real layout issues underneath it.
- Fix hard faults first, then borderline contrast and small hit targets, then everything else.
- Open the actual screenshots. This script catches what breaks a rule — it doesn't catch what simply looks wrong, which is still a human call.
- Check the base URL the run printed before trusting a clean result. A clean run against the wrong server is the most expensive false positive there is.
- When a project has its own measurable rule that isn't here (from `dotfn-system`), add it directly to the project's copy of `checks.js` and write the rule into the project's design skill — don't leave it as prose only one person remembers to check.
