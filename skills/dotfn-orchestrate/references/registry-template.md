# dotfn registry — starter

Copy this file to `~/.dotfn/registry.md` (every project) or `.dotfn/registry.md` (this project only), then replace the example row with your own. `dotfn-orchestrate` checks both locations — see its `SKILL.md` for exactly when and how.

This exists for the skills you already have installed and trust more than `dotfn-stack`'s own built-in defaults for one specific case — a motion library you know well, a language-specific skill, a framework you have strong opinions about. Nothing here is required; an empty or missing registry just means `dotfn-stack` keeps using its own guidance everywhere.

## Format

One row per case. All four columns matter:

- **When** — the situation that should trigger this row, written the way you'd actually describe the task, not a keyword list. Specific enough that an unrelated request doesn't match.
- **Skill** — the exact installed skill name to load. If it isn't actually installed, the row is ignored and a note is made of it.
- **Instead of** — which `dotfn-stack` skill(s) or guidance this replaces or supplements for this case. Name the specific thing being overridden, not "everything."
- **Why** — one line. This is what lets a future you (or a reviewer) tell whether the row still makes sense.

## Example

```markdown
| When | Skill | Instead of | Why |
|---|---|---|---|
| Building or reviewing GSAP timelines or ScrollTrigger | gsap-skill | dotfn-capture's motion recipes, dotfn-taste's motion principles | GSAP has its own easing names, timeline API, and ScrollTrigger conventions that generic CSS motion advice doesn't cover |
```

## A few more shapes this can take, to show the range

```markdown
| When | Skill | Instead of | Why |
|---|---|---|---|
| Writing or reviewing Swift/SwiftUI code | my-swift-skill | nothing in dotfn-stack — this is outside its scope | A dedicated Swift skill with my own conventions beats generic guidance |
| Building a data table with sorting, filtering, or virtualization | my-table-skill | dotfn-taste's generic component guidance | Hand-rolling a table is how you end up reinventing keyboard navigation badly |
| Any copy/microcopy pass on a shipped product (not a prototype) | my-voice-skill | dotfn-taste's Copy section | My own brand voice guide is more specific than this stack's generic copy principles |
```

Delete this example section and keep only your own rows once you've copied this file to its real location.
