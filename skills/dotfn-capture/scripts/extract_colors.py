#!/usr/bin/env python3
"""
extract_colors.py — Dominant colors from a local image

Returns the top-N dominant colors with hex codes and area percentages, via
median-cut color quantization. Use this when vision gives an approximate
color and a token table or an image-generation prompt needs an exact hex.

Usage:
    python extract_colors.py ./reference.png
    python extract_colors.py ./reference.png --top 12 --json -o colors.json

Requirements:
    pip install Pillow
"""

import argparse
import json
import sys
from pathlib import Path


def check_pillow():
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        print("Pillow is not installed.\n\nInstall with:\n    pip install Pillow\n", file=sys.stderr)
        return False


def rgb_to_hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(*rgb[:3])


def extract(image_path, top_n=8, resize=400):
    from PIL import Image

    img = Image.open(image_path).convert("RGB")
    longest = max(img.size)
    if longest > resize:
        scale = resize / longest
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)

    quantized = img.quantize(colors=top_n, method=Image.Quantize.MEDIANCUT)
    palette = quantized.getpalette()
    counts = quantized.getcolors()
    if not counts:
        return []

    total = sum(c for c, _ in counts)
    results = []
    for count, idx in counts:
        rgb = tuple(palette[idx * 3: idx * 3 + 3])
        results.append({"hex": rgb_to_hex(rgb), "rgb": list(rgb), "pct": round(count / total * 100, 2)})
    results.sort(key=lambda c: c["pct"], reverse=True)
    return results


def format_markdown(colors, image_path):
    lines = [f"# Dominant colors — `{image_path}`", "", "| Rank | Hex | RGB | % of area |", "|---|---|---|---|"]
    for i, c in enumerate(colors, 1):
        lines.append(f"| {i} | `{c['hex']}` | {', '.join(map(str, c['rgb']))} | {c['pct']}% |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Extract dominant colors from a local image.")
    parser.add_argument("image")
    parser.add_argument("--top", type=int, default=8)
    parser.add_argument("--resize", type=int, default=400)
    parser.add_argument("--json", dest="as_json", action="store_true")
    parser.add_argument("--output", "-o", default=None)
    args = parser.parse_args()

    if not check_pillow():
        sys.exit(2)

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"Image not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    colors = extract(image_path, top_n=args.top, resize=args.resize)
    if not colors:
        print("No colors extracted — image may be empty or unreadable.", file=sys.stderr)
        sys.exit(1)

    output = (
        json.dumps({"image": str(image_path), "colors": colors}, indent=2)
        if args.as_json else format_markdown(colors, image_path)
    )

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Wrote {len(colors)} colors to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
