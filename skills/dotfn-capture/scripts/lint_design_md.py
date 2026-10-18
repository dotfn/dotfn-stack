#!/usr/bin/env python3
"""
lint_design_md.py — Validate a design.md / element.md against the output contract

Checks that a generated spec has the frontmatter fence and every required
section heading from references/design-md.md (full mode) or references/element-copy.md
(element mode, auto-detected from the `kind:` frontmatter field or forced via
`--element`). When a spec describes `<canvas>`, WebGL, 3D transforms, or spatial
warp motion, also verifies that the three spatial invariants (`Coordinate space`,
`Scale direction`, `Viewport reach`) are locked down explicitly. Also exposes
`contrast_table()`, a small WCAG 2.1 contrast calculator for the "Contrast
check" section — call it from a one-liner, don't hand-compute ratios.

Stdlib only.

Usage:
    python lint_design_md.py design.md
    python lint_design_md.py element.md --element
    python -c "from lint_design_md import contrast_table; print(contrast_table('#111111,#FFFFFF:body'))"
"""

import argparse
import re
import sys
from pathlib import Path

FULL_MODE_HEADINGS = [
    "## Source", "## Summary", "## 1. Identity", "### 1.1 Impression",
    "### 1.2 The one distinguishing thing", "## 2. Tokens", "### 2.1 Color",
    "### 2.2 Type", "### 2.3 Spacing and radius", "### 2.4 Elevation",
    "### 2.5 Contrast check", "## 3. Components", "## 4. Layout",
    "### 4.1 Grid and containers", "### 4.2 Responsive behavior", "## 5. Motion",
    "## 6. Reconstruction guidance", "## 7. Constraints", "### Do", "### Don't",
    "## 8. Open questions", "## 9. Companion files",
]
ELEMENT_BASE_HEADINGS = [
    "## Source & context", "## 1. What it is", "## 6. Confidence",
]
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
KIND_RE = re.compile(r"^\s*kind:\s*([A-Za-z0-9_-]+)", re.MULTILINE)
SPATIAL_TRIGGER_RE = re.compile(
    r"(<canvas\b|\bcanvas\b|\bwebgl2?\b|\bgetContext\b|\bwarp[XY]?\b|\bwarpScaleY\b|"
    r"\btunnel\b|\bperspective\b|\brotate[XYZ]\b|\bscale3d\b|\btranslate3d\b)",
    re.IGNORECASE,
)
SPATIAL_INVARIANTS = [
    ("Coordinate space", re.compile(r"(coordinate\s+space|espacio\s+de\s+coordenadas|screen-space|item-local)", re.IGNORECASE)),
    ("Scale direction", re.compile(r"(scale\s+direction|direcci[oó]n\s+de\s+escala|center\s*(?:->|→)\s*edge|centro\s*(?:->|→)\s*borde)", re.IGNORECASE)),
    ("Viewport reach", re.compile(r"(viewport\s+reach|alcance\s+horizontal|edgePad|fixed\s+item\s+width)", re.IGNORECASE)),
]
VAGUE_VALUE_RE = re.compile(
    r"\b(sky blue|light grey|medium size|some shade of|about \d+ms|probably ease-(?:in|out|in-out)|"
    r"para los costados|achicar un poco|agrandar un poco)\b",
    re.IGNORECASE,
)


def luminance(rgb):
    def chan(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (chan(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def hex_to_rgb(hex_color):
    h = hex_color.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def contrast_ratio(fg_hex, bg_hex):
    l1, l2 = sorted((luminance(hex_to_rgb(fg_hex)), luminance(hex_to_rgb(bg_hex))), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def contrast_table(*pairs):
    """Each pair is 'fg,bg' or 'fg,bg:label'. Returns a markdown table string."""
    rows = ["| Pair | Ratio | AA normal (4.5:1) | AA large (3:1) | AAA normal (7:1) |",
            "|---|---|---|---|---|"]
    for pair in pairs:
        spec, _, label = pair.partition(":")
        fg, bg = (s.strip() for s in spec.split(","))
        ratio = contrast_ratio(fg, bg)
        name = label or f"{fg} on {bg}"
        rows.append(
            f"| {name} | {ratio:.2f}:1 | {'pass' if ratio >= 4.5 else 'FAIL'} | "
            f"{'pass' if ratio >= 3 else 'FAIL'} | {'pass' if ratio >= 7 else 'fail'} |"
        )
    return "\n".join(rows)


def extract_section(text, heading_prefix):
    idx = text.find(heading_prefix)
    if idx == -1:
        return None
    rest = text[idx:]
    next_h2 = re.search(r"\n##\s+", rest[len(heading_prefix):])
    if next_h2:
        return rest[:len(heading_prefix) + next_h2.start()]
    return rest


def lint(path, mode="auto"):
    text = Path(path).read_text(encoding="utf-8")
    issues = []
    checks_run = 0

    checks_run += 1
    fm_match = FRONTMATTER_RE.match(text)
    if not fm_match:
        issues.append("Missing YAML frontmatter fence (--- ... ---) at the top of the file.")
        frontmatter = ""
    else:
        frontmatter = fm_match.group(1)
        checks_run += 1
        if "source:" not in frontmatter and "name:" not in frontmatter:
            issues.append("Frontmatter is missing both `source:` and `name:` — need at least one.")

    kind_match = KIND_RE.search(frontmatter)
    is_element = (mode == "element") or (mode == "auto" and bool(kind_match))

    if is_element:
        checks_run += 1
        kind = kind_match.group(1).lower() if kind_match else None
        if kind not in ("code", "asset", "hybrid"):
            issues.append(
                f"Element mode frontmatter must declare `kind: code | asset | hybrid` (found: {kind!r})."
            )
        required = list(ELEMENT_BASE_HEADINGS)
        if kind in ("code", "hybrid", None):
            required.extend(["## 2. Spec", "## 4. Reconstruction prompt"])
        if kind in ("asset", "hybrid"):
            required.append("## 5. Generative image prompt")
            checks_run += 1
            if "palette:" not in frontmatter:
                issues.append(f"Element mode `kind: {kind}` requires a `palette:` list in frontmatter.")
    else:
        checks_run += 1
        if frontmatter and "version:" not in frontmatter:
            issues.append("Frontmatter is missing a `version:` key.")
        required = list(FULL_MODE_HEADINGS)

    for heading in required:
        checks_run += 1
        if not re.search(rf"^{re.escape(heading)}\b", text, re.MULTILINE):
            issues.append(f"Missing required heading: {heading!r}")

    motion_heading = "## 3. Motion" if is_element else "## 5. Motion"
    motion_section = extract_section(text, motion_heading)
    if not is_element and motion_section is not None:
        checks_run += 1
        if len(motion_section.strip().splitlines()) <= 1:
            issues.append(
                "Section 5 (Motion) is empty — write 'No interactive motion captured' explicitly if that's the finding."
            )

    if motion_section is not None and SPATIAL_TRIGGER_RE.search(motion_section):
        for label, pattern in SPATIAL_INVARIANTS:
            checks_run += 1
            if not pattern.search(motion_section):
                issues.append(
                    f"{motion_heading} mentions spatial/<canvas>/3D deformation but is missing the "
                    f"`{label}` spatial invariant (see references/element-copy.md)."
                )

    checks_run += 1
    hex_literals = re.findall(r"#[0-9A-Fa-f]{3,8}\b", text)
    vague_matches = VAGUE_VALUE_RE.findall(text)
    if vague_matches:
        uniq = sorted({m.lower() for m in vague_matches})
        issues.append(f"Found vague, non-literal value descriptions: {uniq} — use real hex/px/ms/curve values.")

    return issues, len(hex_literals), checks_run


def build_parser():
    parser = argparse.ArgumentParser(
        description="Validate a design.md or element.md spec against the dotfn-capture output contract.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("file", nargs="?", help="Path to design.md or element.md")
    parser.add_argument(
        "--mode", choices=["auto", "full", "element"], default="auto",
        help="Validation mode: auto-detect from `kind:` frontmatter (default), or force full/element.",
    )
    parser.add_argument(
        "--element", action="store_true",
        help="Shorthand for --mode element (validates against references/element-copy.md).",
    )
    parser.add_argument(
        "--contrast", nargs="+", metavar="FG,BG[:LABEL]",
        help="Compute a WCAG 2.1 contrast table for one or more '#FG,#BG:label' pairs instead of linting a file.",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.contrast:
        print(contrast_table(*args.contrast))
        sys.exit(0)

    if not args.file:
        parser.error("a markdown file path is required (or pass --contrast)")

    path = Path(args.file)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    mode = "element" if args.element else args.mode
    issues, hex_count, checks_run = lint(path, mode=mode)
    if issues:
        print(f"{len(issues)} of {checks_run} check(s) failed in {path}:\n")
        for issue in issues:
            print(f"  - {issue}")
        sys.exit(1)

    print(f"{path}: 0 of {checks_run} check(s) failed — contract satisfied ({hex_count} literal hex value(s) found).")
    sys.exit(0)


if __name__ == "__main__":
    main()

