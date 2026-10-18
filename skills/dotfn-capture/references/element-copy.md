# Element mode — copying one piece

Element mode zooms into one visual element instead of a whole page: a navbar, a pricing card, a single illustration, or one specific interaction ("their hover animation on the CTA"). Output is `element.md` — a focused spec plus either a code reconstruction prompt or a generative-image prompt, never both halves padded in when only one applies.

## Classify first: what kind of element is this?

| Kind | What it is | Output |
|:--|:--|:--|
| **`code`** | Rebuildable with HTML/CSS/SVG and stock fonts: navbars, cards, buttons, hero text, footers, badges | A scoped token spec plus a reconstruction prompt |
| **`asset`** | Needs an actual image file: 3D art, photography, a mascot, a hand-drawn illustration | A palette-grounded generative-image prompt |
| **`hybrid`** | A code container holding an asset: a card with an illustration inside, a hero with a photographic background | Both, scoped separately |

Test: *could a competent frontend developer rebuild this with HTML/CSS/SVG and no image file?* Yes → `code`. No → `asset`. The shell is code but it holds something that needs a real image → `hybrid`. When genuinely unsure, call it `hybrid` and say so — splitting the shell from the asset is more useful than misclassifying the whole thing.

**A captured animation is its own thing, not a kind.** If the request is "copy their hover effect" or "how does this transition work", the element is still `code` (or whatever it already is) — the animation is reported in the Motion field below, sourced from Step 3 of the main workflow, never guessed.

## Workflow

### E1 — Identify the target precisely

| Source | Best targeting, in order |
|:--|:--|
| URL | A CSS selector the person gives you → one you infer from the fetched markup → a cropped capture plus a plain description |
| Local image | The whole image is the element, or the person describes a region of it |
| Figma | A `node-id` in the link → the node you locate via `get_metadata` |

A page with a dozen similar cards and an ambiguous reference ("the card") is worth one clarifying question before capturing — guessing wrong wastes the whole run.

### E2 — Capture, scoped to the element

- **URL with a selector**: `python scripts/capture_site.py <URL> --selector "<css-selector>" --output ./element.png` — screenshots only that element's bounding box and saves its `outerHTML`, which carries real classes and structure (and auto-runs `--inspect-canvas` if the element contains a `<canvas>`). If the request touches animation or interaction, add `--motion` (and `--scroll-scrub` when the element sits inside a `position: sticky` scroll runway; see [motion-capture.md](motion-capture.md)). Query any extracted `<canvas>` JS bundles offline with `python scripts/capture_site.py --search-bundles "warp|scaleY|getContext"`.
- **URL, no workable selector**: a full capture, then analyze the element's region visually — say plainly that targeting was visual, which lowers confidence on exact spacing values.
- **Image**: direct vision; run `extract_colors.py` on a crop if the element is (or contains) an `asset` — its output feeds the palette block below directly.
- **Figma**: `get_metadata` → `get_design_context` on the node → `get_screenshot`. Exported fills inside the node usually mean `asset` or `hybrid`.

**Always capture the element's immediate context** — what surface it sits on, the adjacent spacing, the parent background. An element copied without its surrounding context gets rebuilt looking stranded.

### E3 — Scoped analysis

Extract only the tokens and identity cues this element actually exhibits — never pad with page-level analysis (that's full mode's job). One exception: the context captured in E2 belongs here even though it's technically "outside" the element.

**When copying or adapting a spatial/3D deformation or `<canvas>` carousel**, lock down these three axes explicitly in the spec and before coding any requested modification:

| Axis | Option A | Option B | Failure mode if guessed wrong |
|:--|:--|:--|:--|
| **1. Scale direction (center → edge)** | **Tunnel / receding** (`scaleY` shrinks outward, e.g. `1.0 → 0.62` with depth shading) | **Funnel / wide-angle** (`scaleY` expands outward, e.g. `0.60 → 0.97`) | Side cards grow when the person wanted them to shrink into depth (or vice versa) |
| **2. Coordinate space** | **Screen-space field** (`warpY` and shading are functions of `|screenX - centerX|`) | **Item-local space** (`warpY` is a function of each card's own `u ∈ [0, 1]`) | In item-local space, as soon as two cards share one side mid-scroll (`k = n + 0.35`), the outer card's inner edge jumps back up to full height next to its neighbor's shrunken outer edge |
| **3. Viewport reach** | **Viewport-edge stretch** (`warpX` pulls side items out to `viewW - edgePad`) | **Fixed item width** (side items keep a constant `sideWidthRatio * cardW`) | Large empty margins on both sides of the screen when the person expected the distortion to span the viewport |

**When merging two references (e.g., "use the card design from this image with the carousel distortion from that site, but shrinking outward"):**
- **Separate Skin from Engine**: Keep the extracted mathematical engine (`warpX(worldX)`, `warpScaleY(screenX)`, slice loop) intact; replace only the texture/skin painter or change the single target constant (`tunnelMinScaleY = 0.62` instead of `1.62`). Never throw away a working screen-space equation to write a new per-card formula from scratch.
- **Target vs. Current-Bug screenshots**: When the person sends a screenshot saying *"quiero este formato / busco que se achique así"*, that image is the **target** — read its geometry directly (e.g., inner edge tall, outer edge smaller) and match it. Only treat a screenshot as the "wrong" state when the person explicitly labels it *"actualmente se ve así / acá hay un problema"*.

### E4 — Write `element.md`

```markdown
---
name: "[element name]"
source: "[URL / path / Figma link]"
captured: 2026-10-16
kind: code | asset | hybrid
target:
  description: "[how it was identified]"
  selector: "header.navbar"        # when DOM-targeted

# kind: code | hybrid
colors:
  surface: "#FFFFFF"
  text-primary: "#171717"
type:
  label: { family: "Inter, sans-serif", size: 14px, weight: 500 }
spacing-used: [8, 16, 24]

# kind: asset | hybrid
palette:
  - "#5B6CFF"   # dominant, ~40% of area
  - "#0E0E10"   # field color
---

# Element: [name]

## Source & context
- **Targeting**: [selector / node-id / visual region] — [DOM-based ✅ | visual ⚠️]
- **Sits on**: [parent surface color and adjacent spacing]

## 1. What it is
[Two or three sentences: what it is, its job in the parent design, the one thing that makes it distinctive.]

## 2. Spec  (kind: code | hybrid)
- **Structure**: the DOM skeleton, from the captured outerHTML when available
- **Tokens**: the colors / type / spacing / radius this element actually uses
- **States**: observed vs. inferred — mark inferred ones ❓ (hover and focus are easy to miss from a static capture)

## 3. Motion  (only if captured — see motion-capture.md)
- **Trigger & timing**: [the real transition/animation property and value, duration, and the trigger: a pseudo-class (hover/active/focus), a native animation-timeline, a scroll-into-view reveal, a scroll-pinned container, or a click-toggle. Whether it's a plain transition, a named @keyframes animation, `<canvas>`/`requestAnimationFrame`, or library-driven — never a guess.]
- **Spatial invariants** (required whenever the element uses `<canvas>`, WebGL, 3D transforms, or scroll-linked spatial distortion):
  - **Coordinate space**: `screen-space` (`f(|screenX - centerX|)`) | `item-local` (`f(u)` per item)
  - **Scale direction**: `center -> edge: <start> -> <end>` (e.g. `1.0 -> 0.62` receding tunnel vs. `0.60 -> 0.97` expanding funnel)
  - **Viewport reach**: `edgePad: <px or %vw>` (or fixed width ratio)

## 4. Reconstruction prompt  (kind: code | hybrid)
[A paste-ready prompt for a code agent: stack suggestion, the spec inlined, the
context contract ("renders on {colors.surface}"), explicit don'ts.]

## 5. Generative image prompt  (kind: asset | hybrid)
SUBJECT: [concrete and specific — not "an abstract shape"]
STYLE/MEDIUM: [render technique and finish]
COMPOSITION: [framing, angle, negative space]
LIGHTING: [direction, softness, color cast]
PALETTE: [exact hexes from the frontmatter, with roles]
BACKGROUND: [scene — baked-in background, edges blending into the destination surface —
  or isolated — single subject, transparent PNG, generous margin]
AVOID: [negative cues — no text, no watermark, no extra objects]

## 6. Confidence
| Aspect | Confidence | Why |
|:--|:--|:--|
| Targeting | ✅ | DOM selector |
| Motion | ✅/❓ | captured vs. unobserved |

[Open questions, scoped to this element only.]
```

## Delivery format for `asset`/`hybrid`

Decide **before** writing the image prompt how the person will use it — it changes the BACKGROUND block:

| Format | When | Consequence |
|:--|:--|:--|
| `scene` | Regenerating the full composition and mood | Background baked in, edges blend into the destination tone |
| `isolated` | Dropping it into their own site or design | Single subject, transparent PNG, generous margin, no cast ground shadow unless asked |

Default to `isolated` for anything described as "for my site" or "as a PNG." If ambiguous, write the scene version and name the isolated variant as a one-line alternative.

**Isolated prompts need defensive wording.** Prose instructions for transparency are unreliable across image models — lead with the isolation directive ("an isolated asset on a fully transparent background: one single subject, nothing else in the frame"), strip atmosphere words that imply a surrounding world, and close AVOID with "no background of any kind." If a model keeps painting a backdrop anyway, the reliable fallback is a flat chroma background in a color absent from the palette, removed in post.

## Do and don't

**Do**: ground every palette entry in an actual extraction, not an impression; record case and tracking as real typography facts (sentence case vs. tracked all-caps genuinely changes fidelity); capture the integration contract (what it sits on); name the delivery format before writing the prompt; apply confidence markers to the prompt itself.

**Don't**: generate the image — this skill delivers the prompt, rendering is a separate step in the model of the person's choice; expand into a full-page analysis when asked for one element; write any field from imagination rather than from something observed; promise pixel-perfect reproduction — say "expect a couple of iterations" honestly; reproduce brand-identifying artwork (a real logo, a real mascot) for reuse outside documentation — flag it and scope the prompt to style descriptors instead.
