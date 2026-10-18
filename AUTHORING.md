# Authoring contract

This file governs how skills in this repo get written and edited. It is not installed as a skill — it's for whoever (human or agent) adds to `dotfn-stack`.

Every tool call in a long agentic run re-sends the whole conversation so far. A skill that dumps a full HTML page, a full CSS-variable JSON, or an un-cropped full-page screenshot into context pays for that dump again on every later turn. The rules below exist to keep that cost down without losing capability.

## Rules for `SKILL.md`

1. **Decision logic only.** A `SKILL.md` states what to decide and in what order, with the exact values that matter inlined. It does not contain an exhaustive catalog of every possible value — that goes in a `references/*.md` file, loaded only when the decision actually needs it.
2. **The frontmatter `description` does the routing.** State the trigger phrases a user might actually say, and name the adjacent skill to use instead when this one isn't the right fit ("for X use skill Y"). A model deciding which skill to load reads only this line across every installed skill — it has to be precise.
3. **Hard Rules and `Never` tables over prose**, wherever a rule is genuinely checkable. A checklist gets followed and verified; a paragraph of advice gets paraphrased and drifts.
4. **Say what wasn't checked, never report a silent zero.** A count of failures needs its denominator — "0 of 20 checked" means something; "0" alone can mean nothing was looked at.

## Rules for scripts

1. **Print a digest, never the raw dump.** A script that fetches or renders something prints a capped, human-and-model-readable summary to stdout and writes the full data to disk. The digest is what enters context; the full file is there for `grep`/`--search`, never for a wholesale re-read.
2. **Support searching the saved output without re-fetching.** If the full data lives on disk, the same script (or a flag on it) answers a narrow question against that file without hitting the network or the browser again.
3. **Cap screenshots and frames.** A handful of viewport-sized, readable frames beats one full-page image that gets unreadable the moment a vision model downscales it. Default low; let a flag raise it.
4. **Fail loudly on a missing dependency.** Print the exact install command and exit non-zero. Never fall back to a degraded silent path without saying so.
5. **`--help` always works**, even without the optional dependency installed.

## Rules for reference files

- Loaded on demand, not by default — the `SKILL.md` says when to open them.
- Hold the exhaustive version of a table the `SKILL.md` only summarizes: every value, every edge case, every template.
- Keep the same contract (section names, field names) stable across edits where another script or skill parses them by name.

## When a value changes

A shared constant (an easing curve, a spacing scale, a contrast minimum) should exist in exactly one place per skill. If two files in the same skill state the same number, that's a defect — point one at the other instead of keeping both in sync by hand.
