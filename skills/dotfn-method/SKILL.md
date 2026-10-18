---
name: dotfn-method
description: The dotfn loop for agentic design and development work. Use when starting a build from a visual reference (image, URL or Figma file), redesigning an existing product, or deciding what to do next in a design/build/measure cycle. Decides which other dotfn-stack skill to load at each step. Not a requirement — one skill can always be used standalone.
---

# dotfn method

A person brings direction and judgment calls; the agent brings everything that can be captured, measured, or written down. Nothing gets called "done" until it has been measured.

## Entry points

Pick one, in one sentence, before loading anything else.

| Starting point | What you have | Next skill |
|:--|:--|:--|
| **Copy a reference** | A screenshot, a URL, or a Figma file to build from | `dotfn-capture` |
| **Redesign** | A running product whose code already encodes a system | `dotfn-system`, pointed at the live code, before anything else |
| **Build from scratch, no reference** | Just an idea and a brief | Skip capture; go straight to `dotfn-taste` + build |

## The loop

1. **Capture.** A reference (image, site, Figma) becomes a written spec — tokens, components, layout, and (for sites) the motion actually implemented, not a guess. Load `dotfn-capture`.
2. **Systematize.** The spec becomes a skill that lives in the project and governs every screen from here on. Load `dotfn-system`.
3. **Build with taste.** Every screen follows the project's system first, then the general judgment in `dotfn-taste` where the project hasn't decided yet. Before reaching for `dotfn-taste`'s own guidance on something the person has a trusted, more specific skill for — a motion library, a language, a component kind — check the registry described in `dotfn-orchestrate` (`.dotfn/registry.md` or `~/.dotfn/registry.md`); on a match, that skill's guidance wins for that one case. For animation and interaction craft generally, the optional [emilkowalski/skills](https://github.com/emilkowalski/skills) package (`npx skills add emilkowalski/skills`) goes deeper than this stack does — load it if installed, skip it if not, never block on it.
4. **Delegate, if it pays.** Before splitting work across agents, or before building in a domain the registry might cover, load `dotfn-orchestrate`. One agent doing the work well, with this stack's own defaults, stays the baseline.
5. **Measure.** Every screen that changed gets checked in a real browser before anyone looks at it. Load `dotfn-audit`. Fix what it reports first.
6. **Record.** Every correction from the person — "not that color", "too close together", "this should feel instant" — becomes a rule in the project's own skill (written by `dotfn-system`), with its reason. Never a quote; always a principle.

## Rules

- **Survey before asking.** If the code already answers a question (an existing token, an existing route, an existing component), that's never something to ask the person.
- **The person's eye is the last check, never the first.** Send a screenshot or a running build, not a description of one.
- **Change only what was pointed at — and preserve the engine when changing a parameter.** A correction to one screen is not a license to restyle its neighbors, and a request to change a card's visual format or invert one axis of a `<canvas>`/motion effect is not a license to discard the extracted coordinate-space equation and rewrite it from scratch. Swap the skin or flip the constant inside the working formula.
- **A skill here works alone.** Nothing requires the full loop — `dotfn-audit` on an existing project, or `dotfn-capture` on a single component, are complete requests by themselves.

## Done

A step is done when: the spec or the code exists and is readable by the next step, the audit (where applicable) passes with its denominators shown, and anything the person corrected this round is written into the project's own skill as a rule.
