---
name: dotfn-orchestrate
description: Decide whether to split a task across multiple agents and, when it pays, how — plus whether a skill the person already has installed and trusts more than dotfn-stack's own defaults should handle this specific case (their own GSAP skill for GSAP work, a Swift skill for Swift code, and so on). Use before delegating anything, when a task is large enough to parallelize, when running subagents or worktrees, or before writing in a domain the person might have a more specific skill registered for. Delegation is always optional; the default is one agent doing the work well, with dotfn-stack's own defaults.
---

# dotfn orchestrate

One agent doing the work carefully, with dotfn-stack's own defaults, is the baseline. Two different things can change that: splitting the work across several agents, and handing a specific domain to a more specialized skill the person already trusts. Both are tools for when they measurably help — neither is a default posture.

## Decide first

- **Do it directly** when the change is small, when it needs back-and-forth with the person as it goes, when every piece needs the same large chunk of context, or when latency matters more than throughput. Delegating a five-minute task costs more than doing it.
- **Split** when the pieces are genuinely independent — no shared files, no shared state, fixing one doesn't require touching another — when research would otherwise flood the main conversation's context, or when a different tool clearly wins at one piece (a different model, a sandboxed environment, a different runtime).
- **Scale effort to the task.** A single quick call for one fact. A few workers for a genuine comparison. More only for research across many independent areas or a large number of truly separate files. A multi-agent run costs a multiple of what one agent costs — budget for that multiple before starting, not after.

## Delegating to a registered skill, not a subagent

Splitting work across subagents is one kind of delegation. Handing a whole domain to a *different skill* the person already has installed — because it's better at that one thing than anything in `dotfn-stack` — is a different kind, and it happens before any brief gets written.

### The registry

A plain file the person maintains themselves, checked at two locations, project first:

- `.dotfn/registry.md` — this project only.
- `~/.dotfn/registry.md` — every project.

If neither exists, there's nothing registered — continue with `dotfn-stack`'s own defaults and don't mention it again. A starter copy with the format and a worked example lives at [references/registry-template.md](references/registry-template.md); point the person at it the first time they ask to register something.

Format — a markdown table, one row per registered case:

```markdown
| When | Skill | Instead of | Why |
|---|---|---|---|
| Building or reviewing GSAP timelines or ScrollTrigger | gsap-skill | dotfn-capture's motion recipes, dotfn-taste's motion principles | Their own skill knows GSAP's easing names and timeline API; generic CSS advice doesn't apply |
```

### Using it

1. **Before writing in a domain this registry might cover**, check whether either file exists.
2. **Match on judgment, not exact keywords.** "Building or reviewing GSAP timelines" matches a request to add a scroll animation with GSAP even if the person didn't say the word "timeline." A clearly unrelated row doesn't match just because it mentions "animation" too.
3. **On a match**, say so in one line — which row, which skill — then load that skill and let it drive the decision for that piece, instead of (or alongside, per the row's "Instead of" column) `dotfn-stack`'s own guidance. `dotfn-capture`'s motion detection (see its `references/motion-capture.md`) is the most common trigger: it names the library it found, and a registry entry for that same library is the natural next check.
4. **Never invent a match.** If the registry names `gsap-skill` and it isn't actually installed, say so and fall back to `dotfn-stack`'s own defaults — don't pretend to apply guidance from a skill that was never loaded.
5. **A registry entry is the person's call, not a suggestion to second-guess.** If `dotfn-taste` and a registered skill disagree, the registered skill wins for that domain — that's the point of registering it.

## The brief

A worker gets none of the surrounding conversation. Every brief is self-contained and states:

- **Goal and why**, in one or two lines — what "done" looks like and why it matters.
- **Scope** — the exact files or areas the worker owns, and what it must not touch. State hard constraints in the negative when they matter: "do not change the public API," "do not raise any timeout."
- **The relevant project rules**, by path — the project's design skill from `dotfn-system`, any lint config, any existing convention to extend rather than fork.
- **Acceptance** — something observable: a test that passes, a command's output, a screenshot, an audit run. "Looks right" is not an acceptance criterion.
- **Return shape** — short, with paths to artifacts rather than their content pasted in, ending in one explicit status: `DONE`, `DONE_WITH_CONCERNS`, `NEEDS_CONTEXT`, or `BLOCKED`.

## Running workers

- **Launch every independent worker at once, then wait.** Launching one, waiting, then launching the next serializes work that was supposed to run in parallel.
- **Isolate writers.** Two workers never edit the same checkout at the same time — use separate git worktrees, or split ownership so neither one's files overlap with the other's.
- **Pick the model on purpose.** A fast, cheap model for mechanical or high-volume work; the most capable one available for design judgment and final review. Confirm after the run which model actually ran — a request for "the capable one" silently falling back to a cheaper one invalidates the comparison.
- **Long-running work gets launched and checked on separately** — never block a whole session waiting inside the command doing the work. A timeout is a checkpoint to come back to, not proof of failure; a process actually having finished is what justifies stopping or retrying it, not an empty wait.
- **Keep a progress note for anything that spans more than one sitting**, so a compacted context can resume the state instead of restarting from scratch.

## Receiving work back

- **Don't trust the summary.** Read the actual diff, open the actual artifact, run the actual acceptance check. "Done" from a worker is a claim, not evidence.
- **Review in two passes**: first against the brief alone — did it do what was asked, and only that — then for quality. Flag what affects correctness or the stated requirements; let stylistic nitpicking go unless it was in scope.
- **After merging parallel work, re-run the whole check, not just each piece's own.** Two individually-correct pieces can still be wrong together — a shared resource both touched, an assumption both made differently.
- **On failure, resume before restarting.** Retry the same worker once or twice with the missing context filled in; only after that hand it to a fresh worker, possibly with a more capable model.
- **Never quietly fix a worker's output yourself and call the task done.** Either send the correction back to be redone, or fix it openly and say in the report that you did.

## Never

- Delegate specifically to avoid reading the code yourself. Whoever is splitting the work needs to understand the change well enough to split it correctly.
- Leave a worker undecided at the end of a run — reuse it for the next piece, keep it idle for a stated reason, or release it.
- Make the person relay information between two agents. If a handoff between agents is needed, do it directly when it's safe, and only loop the person in when the handoff carries real risk.
- Report a parallel run as faster or better than doing it directly without the actual numbers to back that up.
