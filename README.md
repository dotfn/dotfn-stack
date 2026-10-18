# dotfn-stack

An agentic design/development loop, packaged as skills your coding agent loads on its own: copy a design from a reference, turn it into a system the project remembers, build against it with real criteria, measure every screen before anyone looks at it.

## The loop

| Capture | Systematize | Build | Measure | Record |
|:--|:--|:--|:--|:--|
| A screenshot, a URL or a Figma file becomes a written spec — tokens, components, layout, and the motion actually implemented. | The spec becomes a skill that lives in the project and governs every screen from here on. | Every screen follows the project's system, then general design judgment where the project hasn't decided yet. | Every changed screen is checked in a real browser: contrast, hit areas, spacing, focus, motion. | Every correction becomes a rule in the project's own skill, with its reason. |

## What's inside

Six skills.

| Skill | What it does |
|:--|:--|
| [dotfn-method](skills/dotfn-method/SKILL.md) | The loop itself. Decides which skill to load next, from any entry point. Optional — every skill below also works alone. |
| [dotfn-capture](skills/dotfn-capture/SKILL.md) | Turns an image, a URL, or a Figma file into a `design.md` (full system) or an `element.md` (one component), including CSS motion, `<canvas>`/JS bundle math extraction, sticky scroll-runway scrubbing, and 50% onion-skin visual diffing. |
| [dotfn-taste](skills/dotfn-taste/SKILL.md) | Design judgment: hard limits, priority order, and the overused patterns that mark an interface as generated rather than designed. |
| [dotfn-system](skills/dotfn-system/SKILL.md) | Turns a capture, a set of tokens, or a running codebase into a design skill that lives in the project and overrules ad-hoc code. |
| [dotfn-audit](skills/dotfn-audit/SKILL.md) | Measures rendered screens in a real browser: contrast on the painted color, hit areas, spacing scale, line length, keyboard focus, reduced motion, overflow, zoom — a screenshot per screen and an exit code for CI. |
| [dotfn-orchestrate](skills/dotfn-orchestrate/SKILL.md) | Whether to split work across agents and how, plus a registry so a skill you already trust more — your own GSAP skill, a language skill — handles its one case instead of this stack's defaults. |

## Install

With the [skills CLI](https://skills.sh):

```bash
npx skills add dotfn/dotfn-stack
# or install a single skill:
npx skills add dotfn/dotfn-stack --skill dotfn-capture
```

Or copy the folders inside `skills/` directly to wherever your agent reads skills, then restart it:

| Agent | Personal | Per project |
|:--|:--|:--|
| Claude Code | `~/.claude/skills/` | `.claude/skills/` |
| Codex / Antigravity | `~/.agents/skills/` | `.agents/skills/` |
| Cursor | `~/.cursor/skills/` | `.cursor/skills/` |

`dotfn-capture`'s URL and screenshot flows use Python scripts with two optional dependencies:

```bash
pip install playwright Pillow
playwright install chromium
```

Without them, the skill falls back to direct vision on images and a fetch-only read on URLs, and says plainly which parts of the capture were skipped. Recording a page to catch mount animations, delayed effects, and ambient loops (`record_site.py`) needs `ffmpeg` on `PATH` as well, for pulling changed frames out of the video — `brew install ffmpeg` / `apt install ffmpeg`. The recording itself still works without it; only frame extraction needs it.

`dotfn-audit`'s deeper checks (keyboard focus, forced hover/focus states, reduced motion, screenshots) need Playwright in the *target* project:

```bash
npm i -D playwright-core
npx playwright install chromium
```

Its baseline checks (contrast, text size, hit areas, spacing, overflow) need nothing — they run by pasting `skills/dotfn-audit/scripts/checks.js` into any tool that can evaluate JavaScript on a live page.

## The rest of the stack

`dotfn-method` calls out to one optional add-on at the step where it fits — install it only if you want to go deeper than this stack does on that one topic.

| Add-on | For | Install |
|:--|:--|:--|
| [emilkowalski/skills](https://github.com/emilkowalski/skills) | Motion and interaction craft — building, reviewing, and improving animations, native feel on phones, picking the right UI library. | `npx skills add emilkowalski/skills` |

### Your own skills, registered

That table is one fixed example. For anything else — a motion library you already have a great skill for (GSAP, say), a language-specific skill, a component kind you have strong opinions about — register it yourself instead of waiting for this stack to know about it by name:

1. Copy [`skills/dotfn-orchestrate/references/registry-template.md`](skills/dotfn-orchestrate/references/registry-template.md) to `~/.dotfn/registry.md` (every project) or `.dotfn/registry.md` (this one only).
2. Add a row: when this applies, which installed skill handles it, what it replaces, why.

`dotfn-orchestrate` checks the registry before delegating, and `dotfn-capture`'s motion step checks it the moment it identifies a library (GSAP, Framer Motion, and so on) — on a match, your skill's conventions drive the rebuild instead of this stack's generic defaults.

## Use it

Tell your agent what you're working from:

```text
Copy the design from https://example.com — I want the tokens and the hover
animations on the pricing cards, not just the colors.
```

```text
Here's a screenshot of a card I like. Turn it into something I can build from.
```

```text
Audit the /pricing and /settings routes before I ship this.
```

<br>

MIT licensed. See [LICENSE](LICENSE).
