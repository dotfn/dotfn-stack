---
name: dotfn-taste
description: Design judgment for any interface work — web apps, dashboards, landing pages, forms, mobile screens, redesigns, and reviews. Use when building or reviewing a UI and no project-specific design skill (from dotfn-system) already covers the decision, or when a result looks like a generic AI-generated interface and needs a second pass. Not a replacement for a project's own design skill — that always wins when the two disagree.
---

# dotfn taste

Judgment, not a style. When two interfaces both satisfy a brief, one of them is better, and this skill is how to tell which — and how to not produce the worse one by default.

## Priority order

When two considerations pull against each other, resolve in this order and move on without relitigating it:

1. What the person explicitly asked for.
2. The project's own design skill (from `dotfn-system`), if one exists.
3. The hard limits below — measurable, no exceptions.
4. What the actual people using this screen need to get done.
5. The one visual idea chosen for this specific brief.
6. The defaults in this skill.

## Hard limits

No exceptions, because each is measurable and `dotfn-audit` checks it:

- Text meant to be read is 12px or larger, with contrast of at least 4.5:1 (3:1 at 24px and above).
- Every interactive element has a hit area of at least 44×44px on touch, 24×24px with a pointer.
- Nothing clips, overlaps, or overflows its container at the sizes the brief targets; no horizontal scroll from 320px up.
- Text and icons inside buttons, chips, tabs, and inputs are vertically centered; controls sharing a row share a height.
- Every requirement in the brief is present, usable, and complete — no placeholder states left standing in.
- Inputs have labels, every control is keyboard-reachable with a visible focus state, and zoom is never disabled.

## Before designing anything

- **Who's using this, for what, how often, on what device.** A tool opened fifty times a day earns restraint; a page that only has to persuade once earns more expression.
- **The real content**, including its worst realistic case — a name twice as long as the one in the mock, a list with one item, a list with none, a value that's missing.
- **The product this screen belongs to**, not just the screen itself — its navigation, its secondary actions, the functional details a shipped product already has even when the brief only shows one view.
- **One visual idea**, drawn from what the subject actually is — its materials, its era, its own vocabulary — rather than from how this category of interface usually looks. The idea should explain the color, type, density, and imagery together, as one decision, not four separate ones.

## Principles

**Composition.** One focal point per view, reached through real contrast in scale, weight, and position — not just color. Let content shape the layout: a sequence reads as a sequence, a comparison as a comparison. The same block repeated section after section is the visible seam of a template, not a system.

**Craft.** Commit to one path when two are equally valid; a half-measure read as indecision. Fewer, fully resolved elements beat many half-finished ones. The details nobody asked for — a number that holds still, a border that doesn't shift on hover, a focus ring that was actually designed — are what separate finished from almost.

**Grouping.** Proximity before lines: space inside a group is smaller than space between groups. A shadow belongs to something that floats above the page — a menu, a dialog, a dragged item — not to a static card sitting on a flat page. One separation method per boundary; mixing a border and a background shift and a gap to mark the same seam is three decisions where one was needed.

**Typography.** Pick a typeface for a reason tied to the idea, not by default. Use a small scale with visible steps — body text around 16px on web, denser product UI down to 13–14px, with secondary text staying close to body size rather than trailing off into illegibly small metadata. Keep running lines to 45–75 characters, line-height near 1.5 for text and 1.1–1.25 for headings. Numbers that get compared use tabular figures, right-aligned, with their unit.

**Color.** Assign by role — surface, text at a couple of levels, one accent reserved for action and selection, status colors that never appear without text or an icon next to them. Build any ramp in a perceptual space (OKLCH, not raw RGB interpolation) so steps actually look even.

**Data.** Short identifying values (names, IDs, dates, amounts) stay on one line; long text truncates with the full value reachable somewhere. A value that already identifies itself doesn't need a label stacked on top of it. Nested radii shrink inward as they nest.

**Behavior.** Every view that loads data has a designed loading, empty, and error state — not just the happy path. Every control shows hover, focus, pressed, and disabled, even if some of those differ only slightly. Layouts reflow by priority across sizes, not by uniformly shrinking everything.

**Motion.** Motion explains cause and effect — what appeared, where it came from, that a press registered — and its amount scales inversely with frequency: instant for anything done dozens of times a day, a short transition for the occasional action, one crafted moment for something rare like a first run or a completed task. Entrances come from where they originate (a menu grows from its trigger, a sheet slides from its edge); exits are faster than entrances. Animate `transform`/`opacity`, name the exact properties, and keep motion interruptible so a second click or a reversed hover changes course from wherever it currently is — not from zero.

**Copy.** Buttons name the outcome, not the mechanism. Headings name what the area actually is. The interface doesn't explain itself in a subtitle under every heading — if it needs that much narration, the hierarchy is doing too little work.

## Habits of generated interfaces

These show up often enough in AI-produced UI that they read as the *absence* of a decision rather than a decision. Using one is fine when the brief or the chosen idea genuinely calls for it and you can say why in one sentence — the point is noticing, not a blanket ban.

| Habit | What it looks like |
|:--|:--|
| The default accent | Purple-to-blue or indigo gradients with no brand reason behind them |
| One-hue palettes | Every surface and accent pulled from a single narrow hue family |
| Dark mode by reflex | Near-black backgrounds with a neon accent, picked without checking the product is actually used in low light |
| Decoration for its own sake | Gradient text, glass panels, glow effects, blurred blob shapes, dot-grid backgrounds |
| Cards around everything | Every section boxed in a bordered, shadowed container, sometimes nested inside another card |
| Identical icon rows | Three or more repeated blocks: icon in a tinted square, a title, two lines of caption |
| Stat-tile walls | Big numbers in boxes that aren't actually the point of the screen |
| The template hero | A centered headline, a badge above it, one bolded word, a row of logos underneath |
| Eyebrow labels | Small tracked uppercase text above every heading, whether or not it adds information |
| Pills on ordinary data | Rounded badges wrapped around plain metadata like a date or a count |
| The self-narrating screen | A subtitle under every heading restating what the heading already said |
| Fake chrome | A drawn browser window, phone frame, or terminal dots around content that's already the whole screen |
| Thin border plus big shadow | Both treatments stacked on the same element, when either alone would read as a decision |
| Motion as wallpaper | Fade-and-rise on every section on scroll, a pulsing dot with no state it's representing, a marquee with nothing to announce |

## Before delivering

If the result can be rendered, look at it at the sizes the brief targets before calling it done. Re-check the hard limits, confirm there's one focal point, and scan the habits table above for anything that snuck in without a reason. Fix what's found, then deliver.
