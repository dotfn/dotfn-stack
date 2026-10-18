---
name: dotfn-capture
description: Turn an image, a website URL, or a Figma file into a written design spec — tokens, components, layout, and (for live sites) the motion actually implemented in the CSS, not a guess from a screenshot. Two modes, picked from the request — a whole system ("extract the design from this site") or one element ("copy this navbar", "give me their hover animation"). Use when the user wants to copy, replicate, document, or reverse-engineer a visual design, a single component, or an interaction. For general design judgment once you're building, use dotfn-taste; for turning the resulting spec into a project-living skill, use dotfn-system.
---

# dotfn capture

You are reverse-engineering a design, not describing one. Diagnose it: which values are repeated decisions (tokens) versus one-off choices, which components recur, and — for a live site — which CSS is actually producing the motion the person noticed. The reader of your output is another agent that will rebuild from it, so every claim needs to survive that rebuild.

## Two modes

- **Full mode** (default): the whole design of a page or file → `design.md`. See [references/design-md.md](references/design-md.md).
- **Element mode**: one component ("copy this navbar", "just the pricing card", "their hover animation on the CTA") → `element.md`. See [references/element-copy.md](references/element-copy.md).

Signals for element mode: a definite article plus a single component, an element-scoped verb ("copy", "extract just", "recreate", "get me their..."), or a request scoped to one interaction ("their hover effect", "how this button animates"). Ambiguous requests ("analyze this dashboard") default to full mode, with element mode offered as the natural follow-up.

## Hard rules — the token budget, and three ways this has gone wrong before

A careless run against a real marketing site can burn well over 100k tokens of context on raw HTML and CSS dumps alone. None of that is necessary. But a *cheap* run that quietly misses half the page, invents the copy, or never sees the illustrations is worse than an expensive one — it reports confidently and is wrong. Every rule below exists because it already happened once.

1. **Run scripts, never open their source to understand what they do.** `--help` answers any question about flags.
2. **Never read a saved dump whole.** A stylesheet digest or a rendered HTML save can be 15k–500k tokens. Work from the script's printed digest; for one missing value, search the saved file (every script below supports a `--search`/`--grep` flag) — never parse the JSON yourself.
3. **Cap screenshots, but check the coverage number `capture_site.py` prints.** A handful of viewport-sized, readable frames beats one full-page image that a vision model downscales into noise — but a tall page sampled with too few frames silently skips whole sections. The script computes and prints the real percentage and the exact `--frames` value needed for 100%; when it warns, re-run with that value before treating the capture as complete. (A real run on a 6,986px page with the default frame count covered 50% and missed an entire section — this is not a hypothetical.)
4. **Never trust `WebFetch` (or any summarizing fetch) for exact copy.** It runs the page through a secondary model that can merge, paraphrase, or flat-out misquote text while sounding confident — a real run against this exact failure mode returned a plausible-but-wrong sentence for a component's content that didn't match the live DOM at all. `WebFetch` is fine for orientation (what sections exist, roughly what a page is about) — never for a value that will be presented as verbatim. For verbatim text, read the real DOM: `capture_site.py --save-html` and grep it, or parse it directly.
5. **Run `--find-assets` whenever a component might contain custom artwork**, not just when one is obviously visible. Inline-SVG illustrations are invisible to every other technique here — no `<img src>`, no CSS `background-image`, nothing a token or screenshot pass would catch — and a real run found eight of them on a single page this way, four of which weren't in the original design spec at all because nothing had looked for them.
6. **Generate derived files, never type them by hand.** `design-tokens.json`-shaped output comes from running a script against the written spec, not from retyping values.
7. **Write the spec once**, then fix specific issues with targeted edits — never a full rewrite for one wrong value.
8. **Never eyeball `<canvas>`, WebGL, or procedural JS geometry from a screenshot when the live site is reachable.** Computed-style diffing sees only an empty `<canvas>` box, and guessing a 3D warp curve from pixels takes four rounds of trial and error. When a target element renders in `<canvas>` or via a `requestAnimationFrame` loop, run `capture_site.py <URL> --inspect-canvas` (auto-triggered when `--selector` contains a `<canvas>`) and query the saved JS chunks with `--search-bundles 'warp|scaleY|getContext'` to extract the exact equations (easing polynomials, screen-space warp functions, slice projection, dither matrices).
9. **When merging two references or tweaking one axis of a captured engine, modify the parameter — never rewrite the equation from scratch, and never invert a target reference.** A real run extracted a working screen-space tunnel (`warpX` + `warpScaleY`), then threw it away for a per-card approximation when asked to change the card format and shrink direction — breaking both viewport reach and multi-card tunnel continuity. Worse, it misread the user's target screenshot as a broken state and inverted it. Treat any reference paired with *"quiero este formato / busco esto"* as the target truth (only a screenshot paired with *"actualmente hace esto"* is the bug state), and change only the single constant inside the already-extracted equation.

## Workflow

### Step 1 — Source and emphasis

Identify, asking only if genuinely unclear: which source (image / URL / Figma / a combination), and what the person actually wants out of it — a faithful rebuild, a mood reference, or the underlying system for reuse elsewhere. Default to rebuild-plus-system at standard depth; go deeper only when asked.

**When the request modifies a spatial/3D distortion or combines two references** ("format of image A with the distortion of site B", "distort toward the sides"), natural-language phrases like *"para los costados"* are ambiguous across three independent axes. Resolve all three from the reference image first, or ask in **one** structured question before writing code (see [references/element-copy.md](references/element-copy.md)):
1. **Scale direction (center → edge)**: shrinks toward the outer edges (receding tunnel, e.g. `1.0 → 0.62`) vs. expands toward the outer edges (wide-angle funnel, e.g. `0.60 → 0.97`).
2. **Coordinate space**: **continuous screen-space field** (`f(|screenX - centerX|)`, where every item passing through `screenX` shares the exact same top/bottom tunnel line and shading) vs. **item-local space** (`f(u)` per card, which creates a sawtooth jump when two cards share the same side mid-scroll). Default to screen-space for carousels and reels.
3. **Viewport reach**: side items keep a fixed width vs. stretch horizontally almost to the viewport edges (`viewW - edgePad`).

### Step 2 — Capture

**Image.** View it directly — that's real vision, no script needed. Run `scripts/extract_colors.py <image>` only when you need pixel-exact hex codes rather than a visual estimate (it matters for anything going into a token table or an image-generation prompt).

**URL.** In one turn:

```bash
python scripts/extract_tokens.py <URL>
```

Fetches every linked stylesheet and inline `<style>` block, extracts every `--custom-property` definition *and* every `@keyframes` block, resolves `var()` aliases, buckets by category, and prints a capped digest — the full JSON stays on disk for later searching:

```bash
python scripts/extract_tokens.py --search 'radius|shadow'      # no refetch
python scripts/extract_tokens.py --search 'keyframes' --kind animation
```

Then:

```bash
python scripts/capture_site.py <URL> --viewports desktop,mobile
```

Renders the page in headless Chromium, dismisses the common cookie-banner patterns, saves a few viewport-sized frames spread top to bottom per viewport (never one unreadable full-page PNG), and prints computed styles read straight from the live DOM for body/headings/buttons/inputs/cards — real values, no HTML reading required. **Read the coverage line it prints before moving on** (see Hard Rule 3) — on a long page, re-run with the `--frames` value it names rather than proceeding with a partial capture.

If Playwright isn't installed and the person doesn't want to install it: fetch the URL directly for content and structure, and mark anything that needed rendering (typography, computed spacing) as a lower-confidence estimate rather than silently treating it as measured.

**Figma.** With the Figma connector available: `get_metadata` first (structure, before requesting anything heavy), then `get_variable_defs` (the designer's actual tokens — use these over any inference), then `get_design_context` scoped to one node (never a whole file), then `get_screenshot` for visual reference. If given a whole-file link, ask for a frame or node link instead.

**Combination (Multi-reference merge: A + B).** When the person gives two or more sources (e.g. a live site for the motion/carousel engine plus a screenshot for the visual card format, or a target screenshot vs. a "currently broken" screenshot), state the contract explicitly before editing:
- **Role of each image**: Which image is the **target** (*"quiero este formato / yo busco que..."*) vs. which image shows the **current state to fix** (*"actualmente se agranda / acá hay un problema"*). Never invert what the target screenshot already shows.
- **Skin vs. Engine split**: Which source governs the **visual surface/skin** (colors, typography, card layout) and which governs the **spatial/motion engine** (`warpX`, `warpScaleY`, physics, scroll binding). Keep the engine's coordinate system and equations intact when swapping the skin or flipping a single parameter.

If a source fails (site down, a bot wall, no Figma access, a corrupt image): say so plainly and propose a concrete alternative — a manual screenshot, a narrower node link. Never attempt to bypass a block, and never invent content to fill the gap.

### Step 2.5 — Find the graphics (URL sources, whenever the page has any custom artwork)

```bash
python scripts/capture_site.py <URL> --find-assets --asset-out assets
```

Finds every inline-SVG illustration above the icon-size cutoff (a real illustration's viewBox area runs tens of thousands of px²; a UI icon's runs in the hundreds — the script tells them apart and only extracts the former, to real `.svg` files, named from nearby heading/label text) and lists every real `<img>`/CSS-`background-image` asset, excluding small icons. This is the pass that sees custom artwork — no other technique here does, because it's inline markup, not a `src` URL (see Hard Rule 5). The extracted files are the actual assets; when the capture is for the asset owner's own rebuild, reuse them directly rather than redescribing them as a generative-image prompt (that prompt path is for `element.md`'s `asset` kind — a *different* source's artwork being adapted, see [references/element-copy.md](references/element-copy.md)).

### Step 3 — Capture the motion and the states (URL sources only, when the request touches interaction, animation, or "how does X behave")

A screenshot cannot show you a hover state, a disabled control, an open menu, or which tab is selected — and not every animation is triggered by a pseudo-class, plenty of motion is gated behind a scroll position or a click instead. This step runs five checks, not one, so a scroll-reveal, a disabled button, or a tab selection doesn't get missed just because it never reacts to `:hover`:

```bash
python scripts/capture_site.py <URL> --motion --selector ".pricing-card, button.cta"
```

- **Pseudo-class** (on `--selector`, default interactive elements): forces `:hover`, `:active`, `:focus` and diffs the computed style.
- **Native scroll-driven animation**: checks `animation-timeline` directly — no scrolling needed, this one's just a property read.
- **Scroll-reveal** (on `--scroll-selector`, default `section`/`article`/common reveal-class patterns): scrolls below-the-fold elements into view for real and diffs before vs. after — this is what catches IntersectionObserver-based fade-ins and AOS.
- **Click-toggle and selection** (on `--toggle-selector`, default covers `aria-expanded`/`aria-pressed`/`aria-selected`/`data-state`, `[aria-haspopup]`, `[aria-controls]`, `[role="tab"]`, and `<summary>`): clicks once and diffs — this is what catches accordions, disclosures, tabs, and menus driven by a JS click handler. For an `aria-controls` trigger, it also diffs the *target* element the attribute names, not just the trigger itself — a menu button's own styling can look unchanged while the menu it opens is what actually moved.
- **Disabled state** (on `--disabled-selector`, default `:disabled`/`[aria-disabled]`/`[data-disabled]`): a direct read, no interaction needed — opacity, cursor, color, pointer-events, as they already sit in the DOM.

**When `--motion` (or visual inspection) detects a `<canvas>` or a `position: sticky` scroll-pinned runway**, run the dedicated probes in the same turn (no `ffmpeg` required):

```bash
python scripts/capture_site.py <URL> --inspect-canvas --scroll-scrub --selector ".story"
python scripts/capture_site.py --search-bundles "warp|scaleY|getContext"   # offline query, no refetch
```

- `--inspect-canvas` saves all loaded JS chunks to `./bundles/`, locates the exact chunk and snippet referencing the canvas selector / `getContext` / `requestAnimationFrame` / warp math, and supports offline regex search via `--search-bundles` (with bounded `±180`-char windows so minified 1-line bundles never flood context).
- `--scroll-scrub` detects the sticky scroll runway and captures 5 key progress frames (`p=0.00` rest, `p=0.07` mid-transition $k \approx 0.35$, `p=0.20` next rest, `p=0.50`, `p=1.00`) plus a `<canvas>` vertical span profile at `left 12% | center 50% | right 88%` that directly reports whether the distortion shrinks outward (receding tunnel) or expands outward (funnel).

For each hit, it also reads any `@keyframes` already pulled by `extract_tokens.py` that the element references, and checks for known motion-library signatures (a global object, characteristic data attributes, an inline style pattern a hand-rolled CSS transition wouldn't produce). Full detail on all passes, how to read the result, and what's still genuinely out of reach by diffing alone (Step 3.5 closes most of it): [references/motion-capture.md](references/motion-capture.md).

**When a library gets detected**, before writing the reconstruction prompt in Section 5 of `design.md` (or `element.md`'s Motion field), check whether that same library has a registered skill — `dotfn-orchestrate` explains the registry (`.dotfn/registry.md` / `~/.dotfn/registry.md`). GSAP detected and a `gsap-skill` registered for it means the rebuild should say so explicitly and defer to that skill's conventions rather than writing generic CSS-transition advice for motion that was never CSS to begin with.

Report exactly what was measured (the real easing string, the real duration, the real library if one was detected) versus what's still a visual guess — never present an estimate as a measured value.

### Step 3.5 — Record what diffing can't reach (URL sources, when Step 3 comes back empty on something you can still *see* happening, or the request names a mount animation, a loading/fetch-delayed effect, or an ambient loop)

Every check above works by diffing two snapshots — resting vs. forced, before-scroll vs. after. That's blind to anything that never settles into a clean "after": a mount animation finished before the first probe ever runs, a skeleton that only resolves once a real fetch comes back, a counter ticking up, a pulsing dot or a drifting gradient that loops forever.

```bash
python scripts/record_site.py <URL> --settle 8
```

Records on tape instead of diffing: Playwright starts recording *before* navigation (so a mount animation is captured, not finished by the time anything looks), scrolls top to bottom at a human pace by default (`--no-scroll` to hold one view instead — for a loop or a delayed fetch on content already on screen), then holds for `--settle` seconds so time- and fetch-delayed effects get a chance to fire. ffmpeg then pulls out only the frames where something actually changed — a real timestamp for a discrete moment (a mount firing, a toast appearing), or a representative sample across continuous motion (a drift, a scroll-through) when nothing discrete is there to time. Read only the handful of returned frames, never the whole video.

This is also the pass that caught something no static capture would: a page with scroll-triggered typography-measurement annotations that only exist for a fraction of a second mid-scroll. If a request mentions "the animation when it loads," "what happens while it's loading," or a loop/pulse/drift effect, reach for this before concluding it can't be captured.

Needs `ffmpeg` on `PATH` for frame extraction (the recording itself only needs Playwright) — `brew install ffmpeg` / `apt install ffmpeg`. Without it, the video still saves; extract frames later once it's installed.

### Step 4 — Analyze and write

Read [references/design-md.md](references/design-md.md) (full mode) or [references/element-copy.md](references/element-copy.md) (element mode) now — they hold the section contract, the confidence-marking convention, and the length targets. Then:

1. With two or more text/surface color pairs to check, run the contrast check and cite its summary rather than eyeballing ratios:
   ```bash
   python scripts/lint_design_md.py --contrast '#111,#FFF:body' '#3B82F6,#FFF:link'
   ```
2. Write the spec in one pass (including the `Spatial invariants` block under `## 3. Motion` whenever `<canvas>`, WebGL, or 3D/spatial distortion is involved).
3. `python scripts/lint_design_md.py <file>.md` (or `--element` for `element.md`) and fix anything it flags with a targeted edit, not a rewrite.

### Step 5 — Compare, then deliver

**Before calling it done, run the visual diff and open the composite comparison image.** A text summary loses what the image shows directly: exactly where a surface starts, which edge never carries a background, which lines are decoration versus structure. When rebuilding against a reference screenshot or URL, run:

```bash
python scripts/compare_capture.py <reference.png> <rebuild.png|http://localhost:8090> -o ./compare-diff.png
# or directly during capture:
python scripts/capture_site.py http://localhost:8090 --compare <reference.png> -o ./rebuild.png
```

Inspect both the printed regional similarity (`leftEdge`, `center`, `rightEdge`) and horizontal reach (`leftPad` / `rightPad` in px), and view `compare-diff.png` (`Reference | Rebuild | 50% Onion-Skin + Delta`). Fix any mismatch now, not after delivery.

- **For carousels, reels, and scroll-driven sequences, check two states, never just one**:
  1. **At rest (`k = integer`)**: verify center vs. side proportions, outer viewport margins (`edgePad`), and color/shadow contrast.
  2. **Mid-transition (`k = integer + 0.35`, where two items occupy the same side of the screen)**: verify that the trailing edge of one item and the leading edge of its neighbor follow the **exact same continuous tunnel envelope and shading**, with no vertical step or color jump between them.
- **When serving a local rebuild iteratively**: attach a `ResizeObserver` to every `<canvas>`, schedule `requestAnimationFrame` at the top of the render loop before any early return, and cache-bust local asset links (`script.js?v=N`) so the browser never shows a stale build.

List the files produced and the one obvious next step for what the person asked for — turning the spec into a project skill (`dotfn-system`), refining one weak section, or capturing another element for comparison. Don't close with an open-ended "anything else?".

## Scripts

| Script | Covers | Deps |
|:--|:--|:--|
| `extract_tokens.py` | URL → CSS custom properties and `@keyframes`, as a digest; `--search` queries the saved file without refetching | stdlib only |
| `capture_site.py` | URL → computed styles, viewport frames (with coverage check), `--selector`, `--motion`, `--inspect-canvas` + `--search-bundles` (extract & query `<canvas>`/JS math offline), `--scroll-scrub` (sticky scroll-runway rest & mid-transition capture), `--compare` (onion-skin diff), `--find-assets` | `playwright` (`Pillow` for `--compare`; stdlib only for `--search-bundles`) |
| `compare_capture.py` | Reference image + rebuild image (or live URL) → 3-panel `Reference \| Rebuild \| 50% Onion-Skin + Delta` image, regional similarity %, and horizontal reach (`leftPad`/`rightPad`) check | `Pillow` (`playwright` only when target is a URL) |
| `record_site.py` | URL → a video recorded top-to-bottom (or `--no-scroll`, held on one view), with ffmpeg pulling out only the frames where something changed — for mount animations, fetch-delayed content, and ambient loops that diffing can't reach | `playwright`, `ffmpeg` on `PATH` for frame extraction |
| `extract_colors.py` | Image → dominant hex codes with area % | `Pillow` |
| `lint_design_md.py` | Validates `design.md` or `element.md` (`--element`) against the section/frontmatter/spatial-invariants contract with explicit check counts; `--contrast` computes WCAG contrast tables | stdlib only |

Every script prints its exact install command and exits non-zero if an optional dependency is missing — never a silent degraded run.
