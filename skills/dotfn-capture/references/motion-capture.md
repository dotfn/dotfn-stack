# Motion capture — reading animation out of a live site

A screenshot shows one frame. Most of a site's motion only exists between frames, and that "between" isn't always a pseudo-class — it can be a scroll position, a click that flips a JS state, or a native CSS timeline nobody even needs to interact with to see. This reference covers what `capture_site.py --motion` actually does, how to read its output, and where the technique's honest limits still are.

## The five things `--motion` checks, because motion (and state) isn't only pseudo-class-driven

A CSS pseudo-class (`:hover`, `:active`, `:focus`) is only one of the ways a site triggers motion or signals a state change. `--motion` runs five separate passes so that "no `:hover` transition" doesn't get misreported as "no motion," and "didn't click a button" doesn't get misreported as "no disabled state exists":

### 1. Pseudo-class motion

For elements matching `--selector` (default: links, buttons, `[role="button"]`): read the resting computed `transition`, `animation`, `transform`, `opacity`, `filter`, and `animationTimeline`, then force `:hover` (a real pointer move), `:active` (a held-down pointer), and `:focus` (a real focus call) in turn, re-reading the same properties after each. Any property that changed between the two reads is real, measured motion — never an inference.

### 2. Native CSS scroll-driven animation (no scrolling required to detect)

The same resting read checks `getComputedStyle(el).animationTimeline`. If it's anything other than `auto`, the element is using the modern `animation-timeline: scroll()` or `animation-timeline: view()` CSS feature — a scroll-linked animation that's entirely declarative, with no JavaScript and no `IntersectionObserver` involved. This is reported immediately, without needing to scroll anything, because it's a static property of the element.

### 3. Scroll-reveal (the IntersectionObserver / AOS-style case)

This is the one a pseudo-class genuinely cannot reach, because the trigger is "entered the viewport," not a CSS state. For elements matching `--scroll-selector` (default: `section`, `article`, and common reveal-class patterns like `[data-aos]`, `.fade-in`, `.reveal`) that start out below the fold: read the resting style, then **actually scroll the element into view** — a real scroll, which is what `IntersectionObserver`-based libraries listen for, not a style hack that merely looks the same — wait for the transition to settle, and diff. This is also what catches AOS, which toggles its own `data-aos` state via scroll, and any hand-rolled `IntersectionObserver` fade-in.

### 4. Click-toggle and selection (the JS-driven open/close/selected case)

For elements matching `--toggle-selector` (default: anything carrying `aria-expanded`, `aria-pressed`, `aria-selected`, or `data-state`, plus `[aria-haspopup]`, `[aria-controls]`, `[role="tab"]`, and `<summary>` — the attributes a well-built accordion, disclosure, menu, or tablist already exposes for accessibility, which doubles as a reliable, selector-free way to find these without guessing at a site's class names): read resting, click once, diff, click again to best-effort restore the original state. This is what catches an accordion that animates `max-height`, a tab that changes `aria-selected` on click without touching `aria-expanded` at all, or a menu that animates `transform` on open — motion and state gated behind a JS click handler, not a pseudo-class.

**`aria-controls` gets a second check that matters:** a menu *trigger* button's own styling often doesn't change at all when clicked — the menu it opens, named by the `aria-controls` id, is the element that actually moves or becomes visible. The pass reads that target element's state before and after the click too, and reports it separately (`"via": "aria-controls"` in the result) from whatever changed on the trigger itself. Missing this is how a real open/close interaction gets reported as "no change found" even though clicking it plainly does something.

### 5. Disabled state (no click needed)

For elements matching `--disabled-selector` (default: `:disabled`, `[aria-disabled="true"]`, `[data-disabled]`): a direct computed-style read — `opacity`, `cursor`, `color`, `pointer-events` — no interaction required, because the disabled styling is already sitting in the DOM whether or not anything ever gets clicked. Report it plainly even when it turns out the disabled and enabled states look identical — that's a real finding (the control has no visual disabled treatment at all), not a non-result to skip.

## Resolving what caused the change

Once any of the first three passes reports a diff: if `animation-name` is set and not `none`, the matching `@keyframes` block (already pulled by `extract_tokens.py`) is the source — quote its body. If only `transition` changed, that's a plain CSS transition — quote the exact `property duration timing-function` string. If `animationTimeline` is set, name it directly as a native scroll-driven animation. If none of those explain a visible change, check for a library signature (next section) before concluding "unexplained — likely a JS animation loop, not CSS."

The driver also reloads once under `prefers-reduced-motion: reduce` and re-reads the same elements, so the report can say whether the site actually respects it or the motion persists regardless.

## Reading the result

Report three things per animated element, never fewer:

- **The exact value** — the real `transition` string or the real `@keyframes` body, not a paraphrase ("ease-out, about 200ms" is not acceptable when the real value is `cubic-bezier(0.16, 1, 0.3, 1) 180ms`).
- **The trigger** — which forced state produced the change (`:hover`, `:active`, `:focus`, or none — meaning it's driven by something other than a pseudo-class, likely JS on scroll or mount).
- **The confidence** — ✅ measured (a real computed-style diff) versus ❓ inferred (a library was detected but its exact runtime values weren't captured, because they're generated in JS rather than declared in CSS).

"No measurable change on hover/active/focus" is a complete, honest finding for an element that only *looks* animated in a screenshot (a static shadow, a static gradient) — say so rather than inventing a transition that isn't there.

## Detecting a motion library

CSS alone can't always tell you *how* a site produces its motion — a JS library can animate inline styles directly, leaving no `transition`/`animation` property to read at all. Check for these signatures, in order, before giving up on an element that visibly moves but shows no CSS motion:

| Signature | Library (usual) |
|:--|:--|
| A global `window.__NEXT_DATA__`-adjacent bundle plus elements with inline `style="transform: ..."` that changes on every interaction, no matching CSS rule | Framer Motion / Motion |
| A global `gsap` or `TweenMax`/`TimelineMax` object; elements with `will-change: transform` set inline rather than in a stylesheet | GSAP |
| `data-aos`, `data-aos-duration`, `data-aos-delay` attributes on static content | AOS (Animate On Scroll) |
| `<lottie-player>` tag, or a fetch to a `.json` file whose content starts with `{"v":`, `"ip":`, `"op":` (Lottie's own keys) | Lottie |
| `<canvas>` element with `getContext("2d" \| "webgl" \| "webgl2")` and a `requestAnimationFrame` render loop | Procedural `<canvas>` / WebGL — CSS diffing sees nothing inside the canvas; run `capture_site.py <URL> --inspect-canvas` and query the saved JS chunks with `--search-bundles 'warp|scaleY|getContext'` to read the exact warp, easing, and shader/slice math |
| `position: sticky` element inside a tall scroll wrapper (`parent.offsetHeight > 1.3 * innerHeight`) | Scroll-pinned runway (carousel, story reel, scrollytelling stage) — run `capture_site.py <URL> --scroll-scrub --selector <sel>` to capture rest (`p=0.00`), mid-transition (`p=0.07`), and next-rest (`p=0.20`) states plus the `<canvas>` edge-to-center vertical span ratio |
| Inline `style` attributes that change but match no stylesheet rule, with no library global found | A hand-rolled `requestAnimationFrame` or Web Animations API (`element.animate()`) loop — run `--inspect-canvas` / `--search-bundles` for the element's selector/class to recover the exact curve if the bundle is accessible |
| Only CSS `transition`/`animation-name` changed, nothing inline | Plain CSS — the common and simplest case; quote the exact value |

Name the detected library in Section 5 of `design.md` or the Motion field of `element.md`, and say what signaled it — never state a library with no cited signature.

## Honest limits (of diffing — `--inspect-canvas`, `--scroll-scrub`, and `record_site.py` close most of these)

Diffing two snapshots has a structural blind spot: anything that doesn't settle into a clean "after" never shows up as a diff at all. The limits this used to list are now a flag or `record_site.py` run away rather than a dead end — see [SKILL.md Step 3 & Step 3.5](../SKILL.md):

- **One-shot mount/entrance animations** (a hero that animates in once, on first paint) are finished before any diff-based probe starts measuring — the page settles for roughly a second before any read happens, and most entrance animations are well under that. `record_site.py` starts recording *before* navigation specifically for this case, and a real run caught exactly this: two scene-change moments at 0.5s and 0.7s into a page load, the hero content fading in.
- **Loading, empty, and error states** generally can't be *triggered* from outside the app — they still need a slow network, an empty account, or a failed request, which no script here controls. But if the person already has the state on screen (a slow endpoint that's visibly loading right now), `record_site.py --no-scroll` holds the camera on it and catches the transition when it resolves — it just can't manufacture the slow network itself.
- **Ambient loops that never produce a single "after" state** (a pulsing dot, a drifting gradient, a `blobDrift`-style background) are invisible to every diff pass — there's no resting state distinct from any other moment. `record_site.py` catches these as a representative sample across the loop instead of a before/after pair.
- **`<canvas>`, WebGL, and procedural `requestAnimationFrame` loops** are opaque to DOM computed-style reads, but when the live URL is public, their exact math is sitting in the page's static JS chunks (`/_next/static/immutable/chunks/*.js`, `/assets/*.js`). `capture_site.py --inspect-canvas` downloads every loaded script to `./bundles/` and prints bounded snippets where the canvas selector, `getContext`, or warp math appears; `--search-bundles <REGEX>` queries those saved bundles offline without dumping minified lines into context.
- **Sticky scroll-pinned sequences** (where scrolling drives a continuous parameter $k$ across multiple virtual viewports) are missed by a single static screenshot and don't require `ffmpeg` to inspect: `capture_site.py --scroll-scrub` samples `p=0.00` (rest), `p=0.07` (mid-transition $k \approx 0.35$, where two items share one side of the screen), `p=0.20` (next item at rest), `p=0.50`, and `p=1.00`, and measures the `<canvas>` vertical span at `left 12% | center 50% | right 88%` to classify receding tunnel (`edge/center < 0.92`) vs. expanding funnel (`edge/center > 1.08`).

What's still genuinely out of reach, recording included:

- **A toggle with zero ARIA signal and no `aria-controls`** — a custom dropdown that only ever flips a bare class name like `.open` on itself, with nothing naming what it affects — still won't be found by the default `--toggle-selector`. If the person names the specific element, pass its selector explicitly.
- **A scroll-reveal effect gated on a very specific scroll position** (not simply "entered the viewport" or a sticky runway, but an arbitrary scroll trigger) may still read as unchanged in the diff pass if `scroll_into_view_if_needed()` lands the element somewhere other than that exact trigger point — `record_site.py`'s continuous scroll is the more reliable check when this matters.
- A library-driven animation's *existence* is reliably detectable; when its parameters live inside an opaque third-party runtime rather than the component's own chunk, report "library-driven, exact values not captured" rather than presenting a plausible-sounding guess as the real number.
