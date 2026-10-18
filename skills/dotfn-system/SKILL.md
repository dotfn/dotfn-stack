---
name: dotfn-system
description: Turn a captured design spec (from dotfn-capture), a set of tokens, or an existing running codebase into a design skill that lives inside the project and governs every screen. Use when a project gets its visual system for the first time, when the system changes, or when the project's design doc has drifted from what the code actually does. For the capture step that feeds this, use dotfn-capture; for general judgment outside any one project, use dotfn-taste.
---

# dotfn system

A project's design system is a skill, not a document someone has to remember to open. It lives where the agent already looks, it loads itself, and when a screen disagrees with it, the screen is wrong — not the other way around.

## Where it lives

- `.claude/skills/<project>-design/SKILL.md` for Claude Code, `.agents/skills/<project>-design/SKILL.md` for Codex, `.cursor/skills/<project>-design/SKILL.md` for Cursor — `<project>` is the project's short name, lowercase. If several agents share the project, keep exactly one real file; a tool that "links" skills by copying them silently produces two files that drift apart.
- The frontmatter `description` names every trigger: touching any screen or component, choosing a color/space/type/motion value, and before calling any screen finished.
- An old, separate `DESIGN.md` stays only as history, with its first line saying plainly it's no longer the source of truth.

## Where the values come from

1. **The running code, first**, when it exists: the global stylesheet, the theme object, the base components. Describe what's actually there, not what the original intent was.
2. **A `design.md` from `dotfn-capture`**, when the code doesn't exist yet or is being replaced. Mark anything not yet confirmed in the code as still open.
3. **Never from a palette typed into the skill directly.** Screens ask for roles (`surface`, `text-primary`, `accent`) that resolve to a variable — never a raw hex inline in a component. Trying a new palette should cost exactly one file.

## Sections

Use the ones the project actually needs, in this order — skip what doesn't apply, never pad a section with nothing to say:

1. **Surfaces.** What screens exist, who uses each one, and in what state (logged in, loading, empty).
2. **Brand gesture.** The one thing — a color, a shape, a typographic move — that belongs only to this product, and exactly where it's allowed to show up.
3. **Color.** Roles, the measured contrast rule for text on each surface, where color is used and where it's deliberately never used.
4. **Type and numbers.** Faces, the scale, weights, and the specific face used for figures (tabular, every digit the same width) when numbers get compared.
5. **Space, shape, depth.** The spacing scale, the radius scale with its nesting rule (an inner radius is the outer radius minus the inset), and the shadow tiers, lit from one consistent direction.
6. **Motion.** What moves, for how long, with which curve — pulled from what `dotfn-capture` actually measured on a reference, not a textbook default, when one was captured. What happens under reduced motion.
7. **Navigation.** What's persistent, what collapses, where the primary action lives per device.
8. **States.** Loading, empty, sparse, dense, and error, for every view that loads data.
9. **Focus, keyboard, touch.** The focus treatment per surface, hit-area minimums, zoom left untouched.
10. **Writing.** Register, units, what the interface never says about itself.
11. **Rejected on sight.** What's been turned down already, each with the reason given at the time — this is where `dotfn-taste`'s habits-to-avoid list gets project-specific teeth.
12. **Known traps.** Bugs and false readings already paid for once, so nobody pays for them twice.
13. **Still open.** Decisions the project hasn't made yet. An agent doesn't make these unilaterally — it flags them.
14. **Before calling it done.** The short list of things `dotfn-audit` can't check by itself, so a human knows to look.

## Enforcing the design-token discipline

This is the part that keeps "optimize the design tokens" from being a one-time cleanup that rots:

- Every color, spacing, and type value in the project resolves to a **named role**, never a literal baked into a component. If a component has `color: #171717` inline instead of `var(--text-primary)` or the project's equivalent, that's a defect to fix here, not a style choice to leave alone.
- Any rule that can actually be **measured** (the spacing scale's exact values, the minimum text size, the allowed icon sizes, the line-length range) gets written into `dotfn-audit`'s config in the same change that adds it to this skill — a rule that only exists in prose depends on someone reading it before every screen.
- When the running code and this skill disagree and the code turns out to be right, update the skill in the same change — never leave the skill describing an aspiration the code doesn't match.

## Keeping it true

- Every correction a person makes becomes a rule in Section 11 or 12, written as a principle with its reason — never as a direct quote of what they said.
- Long is fine here. This skill holds facts about one specific product; general craft that applies everywhere else belongs in `dotfn-taste`, not duplicated here.
- When this skill and `dotfn-taste` disagree, this skill wins — it's the more specific, more recently corrected source.
