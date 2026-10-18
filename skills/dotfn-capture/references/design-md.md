# design.md — the full-mode output contract

One reference for Step 4 of the main workflow: what the written spec contains, how confident to sound, and how long each part should run.

## Confidence markers

Every claim that matters carries one:

- ✅ **high** — read directly: a CSS custom property, a computed style, a Figma variable.
- ⚠️ **medium** — a well-grounded inference: a font recognized by eye, a spacing base inferred from repeated distances.
- ❓ **low** — speculation, stated as such, never hidden inside a confident sentence.

Real values only — `#3B82F6`, `16px`, `Inter` — never "sky blue" or "medium-sized". "Modern and clean" is not analysis; name the specific thing that produces that impression (generous whitespace, a single accent color, consistent 8px spacing).

## Depth

**Standard** (default): every section present, at the length given below — enough for another agent to rebuild from. **Deep**, only when asked ("exhaustive", "full brand documentation"): Identity goes deeper, everything else stays standard. A capped section that names specifics beats a long one that pads with adjectives.

## Token rigor

A **token** is a value that repeats as a deliberate decision — seen once, it's just a value; seen three or more times, it's probably a token. CSS custom properties and computed styles are ✅ by default. Use **semantic roles**, not raw indices: `primary` (the action color), `surface` / `surface-raised` (page vs. card background), `text-primary` / `text-muted`, `border`, plus feedback roles (`success`, `warning`, `danger`) only where actually observed. Keep a numeric scale as a scale (e.g. `gray-100`...`gray-900`) when the source already has one — don't collapse it to a single value.

## Frontmatter — the single source of truth for values

The body references the frontmatter as `{group.name}` followed by the literal value inline, e.g. `{colors.primary}` (#171717). Any top-level map is a valid group.

```yaml
---
version: dotfn-capture-1
name: Example
source: https://example.com
captured: 2026-10-16
summary: |
  Two or three sentences of overall impression an agent should read before anything else.
colors:
  primary: "#171717"
  surface: "#FFFFFF"
  surface-raised: "#FAFAFA"
  text-primary: "#171717"
  text-muted: "#6B6B6B"
  border: "#EBEBEB"
type:
  display: { family: "Geist, sans-serif", size: 48px, weight: 600, tracking: -0.02em }
  body: { family: "Geist, sans-serif", size: 16px, weight: 400, lineHeight: 1.5 }
spacing:
  base: 4px
  scale: [4, 8, 12, 16, 24, 32, 48, 64]
radius:
  sm: 6px
  lg: 12px
motion:
  ease-standard: "cubic-bezier(0.23, 1, 0.32, 1)"
  duration-fast: 150ms
components:
  button-primary: { background: "{colors.primary}", color: "{colors.surface}", radius: "{radius.sm}" }
---
```

Every key under `components` gets exactly one matching heading in Section 3 (`#### button-primary`). Every key under `motion` traces to something actually captured in Step 3 of the workflow, never a textbook default.

## Body sections

Fixed names and order — `lint_design_md.py` checks for them by heading text.

```markdown
# Design capture: <name>

> Captured with dotfn-capture. Date: <date>. Emphasis: <rebuild | reference | system>

## Source
## Summary
## 1. Identity
### 1.1 Impression
### 1.2 The one distinguishing thing
## 2. Tokens
### 2.1 Color
### 2.2 Type
### 2.3 Spacing and radius
### 2.4 Elevation
### 2.5 Contrast check
## 3. Components
## 4. Layout
### 4.1 Grid and containers
### 4.2 Responsive behavior
## 5. Motion
## 6. Reconstruction guidance
## 7. Constraints
### Do
### Don't
## 8. Open questions
## 9. Companion files
```

### Source and Summary

Source: type, URL or path, exactly how it was captured ("CSS/keyframes digest + rendered frames, desktop and mobile"), and any limitation ("no Figma access; typography read from computed styles only"). Summary: what this design is for, its overall personality, and one thing a rebuild has to get right or the whole thing reads wrong.

### 1. Identity

**1.1 Impression** — up to five adjectives backed by a specific observation each, plus the closest stylistic reference point if one applies ("reads like a developer tool: dense, monospace numerals, almost no color").

**1.2 The one distinguishing thing** — the single element that would still say "this is that design" if everything else went generic: one color used exactly once and deliberately, one typographic move, one geometric habit. State what it is, where it appears, and where it's deliberately absent. A genuinely generic design has none — say so rather than inventing one.

### 2. Tokens

- **2.1 Color** — a table: `Token | Value | Role | Where it appears | Confidence`. Up to 12 rows; a full numeric scale lives in the frontmatter, not repeated here. A second table for dark mode if one was observed.
- **2.2 Type** — detected family with confidence and its fallback stack, then a table `Token | Size | Weight | Line-height | Use`. Note anything deliberate: negative tracking on display sizes, a tight heading line-height.
- **2.3 Spacing and radius** — the inferred base unit, the multiples actually observed (not a textbook scale), and whether radius is one value, a tiered system (button < card), or deliberately mixed.
- **2.4 Elevation** — a short tier table (`Level | Treatment | Use`) if shadows exist; one tier, or "flat by design, no shadows observed," is a complete answer.
- **2.5 Contrast check** — with two or more text/surface pairs available, run the contrast check from `lint_design_md.py` and quote its pass/fail lines. Fewer pairs: omit and say why.

### 3. Components

One `####` heading per frontmatter `components` key. Each gets: variants actually observed, states observed vs. inferred (mark inferred ones ❓ — hover and focus are easy to miss from a static capture), and the padding/radius/color values with their confidence. Up to six components for standard depth; computed styles from the capture give exact values, so use them rather than eyeballing the screenshot.

### 4. Layout

**4.1** Max width, gutter, vertical rhythm between sections, and what carries hierarchy (size, weight, color, or space — name the actual mechanism). **4.2** Breakpoints only for the viewports actually captured; mark anything else ❓ and suggest re-running with more viewports. Note `clamp()` usage (fluid type) and whether touch targets clear 44px where it matters.

### 5. Motion

This section exists because a static capture misses it by default — fill it only from what Step 3 of the workflow actually measured, never from how the screenshot "feels." Motion isn't only `:hover` — group findings by which of the four capture passes found them (pseudo-class, native scroll-timeline, scroll-reveal, click-toggle), since each implies a different thing to rebuild.

For every element with measured motion: the real `transition`/`animation` property and value (not a guess at "probably ease-out"), the duration, the trigger (hover/active/focus, a scroll into view, or a click), and whether it's a plain CSS transition, a declared `@keyframes` animation (name it, show the body if short), a native `animation-timeline` scroll-driven animation (quote the timeline value directly), or driven by a detected library (name which one, say what signaled it). No elements found to animate under any of the four passes → "No motion captured" is a complete, honest answer — never pad it with assumed defaults.

### 6. Reconstruction guidance

A suggested stack with one line of evidence (framework class-name signals, a detected library). Up to three quick wins. Up to four tricky parts (licensed fonts, a library dependency implied by Section 5, an unusual layout). States still needing a decision (loading, empty, error) named in one line each.

### 7. Constraints

Each rule names a token and traces to an observation — "reserve `{colors.primary}` for the one conversion action, never as a card background" is a rule; "use primary for CTAs" is filler. Up to five Do and five Don't. Fewer than three grounded rules on either side → write "not enough evidence for brand-specific rules yet" instead of padding to five.

### 8. Open questions

What couldn't be determined, and what material would settle it. None → "material sufficient for a complete rebuild."

### 9. Companion files

One line per generated file: the validated spec itself, any contrast report, which capture frames were used as evidence.

## Before writing: a last pass

After analyzing and before writing, check once for: light/dark banding across sections, two coexisting scales kept in separate contexts on purpose (tight radius on controls, pill radius on CTAs), a single chromatic accent in an otherwise neutral palette, and whether the hero is centered or split — these are the patterns Section 7's rules should capture, not new sections of their own.
