#!/usr/bin/env python3
"""
compare_capture.py — Visual comparison, horizontal reach check, and onion-skin diff

Compares a reference image against either a local rebuild image or a live URL
(rendered via Playwright at the exact dimensions of the reference image).
Produces:

  1. A quantitative digest on stdout:
     - Overall similarity % and pixel Mean Absolute Error (MAE)
     - Regional similarity (left edge 18%, center 40%, right edge 18%) so a
       side-tunnel or margin mismatch is never hidden by a matching center
     - Horizontal content reach (leftPad / rightPad in px from the background)
       comparing where the reference's outer elements stop vs. the rebuild
  2. A composite visual inspection image (Reference | Rebuild | 50% Onion-Skin +
     magenta delta highlight) saved to disk for Step 5 verification.

Usage:
    python compare_capture.py ref.png actual.png
    python compare_capture.py ref.png http://localhost:8090 --output ./diff.png
    python compare_capture.py ref.png http://localhost:8090 --selector "#reel-canvas"

Requirements:
    pip install Pillow
    pip install playwright && playwright install chromium  (only when target is a URL)
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
        print(
            "Pillow is not installed.\n\nInstall with:\n    pip install Pillow\n",
            file=sys.stderr,
        )
        return False


def check_playwright():
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        print(
            "Playwright is not installed (required when comparing against a live URL).\n\n"
            "Install with:\n    pip install playwright\n    playwright install chromium\n",
            file=sys.stderr,
        )
        return False


def is_url(target):
    return target.startswith(("http://", "https://", "file://"))


def capture_target_url(url, ref_size, out_path, selector=None, scroll_y=None, wait_ms=600):
    from playwright.sync_api import sync_playwright

    w, h = ref_size
    # Ensure a reasonable minimum viewport if the reference is a small cropped element
    vw = max(w, 1280 if selector else w)
    vh = max(h, 800 if selector else h)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": vw, "height": vh})
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
        if scroll_y is not None:
            page.evaluate(f"window.scrollTo(0, {int(scroll_y)})")
        page.wait_for_timeout(wait_ms)

        if selector:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=10000)
            locator.scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            locator.screenshot(path=str(out_path))
        else:
            page.screenshot(path=str(out_path))
        browser.close()
    return out_path


def _estimate_bg_color(img):
    """Estimate background RGB from the four corners of the image."""
    w, h = img.size
    corners = [
        img.getpixel((2, 2)),
        img.getpixel((max(0, w - 3), 2)),
        img.getpixel((2, max(0, h - 3))),
        img.getpixel((max(0, w - 3), max(0, h - 3))),
    ]
    r = round(sum(c[0] for c in corners) / 4)
    g = round(sum(c[1] for c in corners) / 4)
    b = round(sum(c[2] for c in corners) / 4)
    return (r, g, b)


def _measure_horizontal_bounds(img, threshold=24):
    """Find leftmost and rightmost x columns that differ from the corner background
    Across the middle 60% vertical band (ignoring top/bottom navbars or footers)."""
    w, h = img.size
    bg = _estimate_bg_color(img)
    y_start = int(h * 0.20)
    y_end = max(y_start + 1, int(h * 0.80))
    step_y = max(1, (y_end - y_start) // 80)

    left_x = w
    right_x = 0
    for x in range(w):
        active = False
        for y in range(y_start, y_end, step_y):
            px = img.getpixel((x, y))
            dist = abs(px[0] - bg[0]) + abs(px[1] - bg[1]) + abs(px[2] - bg[2])
            if dist > threshold:
                active = True
                break
        if active:
            if x < left_x:
                left_x = x
            if x > right_x:
                right_x = x

    if left_x > right_x:
        return {"leftPad": 0, "rightPad": 0, "spanWidth": w, "spanPct": 100.0}

    span = right_x - left_x + 1
    return {
        "leftPad": left_x,
        "rightPad": max(0, w - 1 - right_x),
        "spanWidth": span,
        "spanPct": round(span / w * 100, 1),
    }


def _region_mae(diff_img, box):
    crop = diff_img.crop(box)
    hist = crop.histogram()
    # 3 channels of 256 bins each
    total_pixels = max(1, (box[2] - box[0]) * (box[3] - box[1]) * 3)
    weighted_sum = 0
    for ch in range(3):
        ch_hist = hist[ch * 256:(ch + 1) * 256]
        for val, count in enumerate(ch_hist):
            weighted_sum += val * count
    return weighted_sum / total_pixels


def compare_images(ref_path, actual_path, output_path, delta_threshold=28):
    from PIL import Image, ImageChops, ImageDraw

    ref_img = Image.open(ref_path).convert("RGB")
    act_raw = Image.open(actual_path).convert("RGB")
    ref_w, ref_h = ref_img.size
    act_w, act_h = act_raw.size

    resized = (act_w, act_h) != (ref_w, ref_h)
    act_img = act_raw.resize((ref_w, ref_h), Image.LANCZOS) if resized else act_raw

    diff = ImageChops.difference(ref_img, act_img)
    overall_mae = _region_mae(diff, (0, 0, ref_w, ref_h))
    left_mae = _region_mae(diff, (0, 0, max(1, int(ref_w * 0.18)), ref_h))
    center_mae = _region_mae(diff, (int(ref_w * 0.30), 0, max(int(ref_w * 0.30) + 1, int(ref_w * 0.70)), ref_h))
    right_mae = _region_mae(diff, (int(ref_w * 0.82), 0, ref_w, ref_h))

    def sim_pct(mae):
        return round(max(0.0, 100.0 - (mae / 255.0) * 100.0), 1)

    ref_bounds = _measure_horizontal_bounds(ref_img)
    act_bounds = _measure_horizontal_bounds(act_img)

    # Build 50/50 onion-skin panel with magenta highlight where pixel delta > delta_threshold
    onion = Image.blend(ref_img, act_img, alpha=0.5)
    gray_diff = diff.convert("L")
    mask = gray_diff.point(lambda p: 190 if p > delta_threshold else 0)
    highlight = Image.new("RGB", (ref_w, ref_h), (255, 0, 128))
    onion_highlighted = Image.composite(highlight, onion, mask)

    # Assemble a 3-panel composite (Reference | Rebuild | 50% Onion-Skin + Delta)
    header_h = 28
    gap = 8
    comp_w = ref_w * 3 + gap * 2
    comp_h = ref_h + header_h
    composite = Image.new("RGB", (comp_w, comp_h), (18, 18, 20))
    draw = ImageDraw.Draw(composite)

    panels = [
        (0, f"1. REFERENCE ({ref_w}x{ref_h})", ref_img),
        (ref_w + gap, f"2. REBUILD ({act_w}x{act_h})", act_img),
        ((ref_w + gap) * 2, f"3. ONION-SKIN 50% + DELTA ({sim_pct(overall_mae)}% match)", onion_highlighted),
    ]
    for x_off, title, panel_img in panels:
        draw.text((x_off + 10, 7), title, fill=(235, 235, 240))
        composite.paste(panel_img, (x_off, header_h))

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    composite.save(output_path)

    warnings = []
    pad_delta_left = abs(ref_bounds["leftPad"] - act_bounds["leftPad"])
    pad_delta_right = abs(ref_bounds["rightPad"] - act_bounds["rightPad"])
    if pad_delta_left > max(24, int(ref_w * 0.03)) or pad_delta_right > max(24, int(ref_w * 0.03)):
        warnings.append(
            f"Horizontal reach mismatch: reference pads (L={ref_bounds['leftPad']}px, R={ref_bounds['rightPad']}px, "
            f"span={ref_bounds['spanPct']}%) vs. rebuild pads (L={act_bounds['leftPad']}px, R={act_bounds['rightPad']}px, "
            f"span={act_bounds['spanPct']}%). Check edgePad / warpX viewport reach."
        )
    edge_sim = min(sim_pct(left_mae), sim_pct(right_mae))
    if sim_pct(center_mae) - edge_sim > 8.0:
        warnings.append(
            f"Side-edge divergence: center matches at {sim_pct(center_mae)}%, but outer edges drop to "
            f"{edge_sim}% (L={sim_pct(left_mae)}%, R={sim_pct(right_mae)}%). Check scaleY direction and screen-space tunnel curve."
        )

    return {
        "reference": str(ref_path),
        "actual": str(actual_path),
        "diffImage": str(output_path),
        "referenceSize": [ref_w, ref_h],
        "actualSize": [act_w, act_h],
        "resizedToMatch": resized,
        "similarityPct": {
            "overall": sim_pct(overall_mae),
            "leftEdge": sim_pct(left_mae),
            "center": sim_pct(center_mae),
            "rightEdge": sim_pct(right_mae),
        },
        "mae": {
            "overall": round(overall_mae, 2),
            "leftEdge": round(left_mae, 2),
            "center": round(center_mae, 2),
            "rightEdge": round(right_mae, 2),
        },
        "horizontalReach": {
            "reference": ref_bounds,
            "actual": act_bounds,
        },
        "warnings": warnings,
    }


def print_compare_report(report):
    sim = report["similarityPct"]
    reach_ref = report["horizontalReach"]["reference"]
    reach_act = report["horizontalReach"]["actual"]
    print(f"   Visual comparison saved: {report['diffImage']}")
    print(
        f"   Similarity: {sim['overall']}% overall  "
        f"(left edge: {sim['leftEdge']}%, center: {sim['center']}%, right edge: {sim['rightEdge']}%)"
    )
    print(
        f"   Horizontal reach (middle 60% band): "
        f"ref L={reach_ref['leftPad']}px R={reach_ref['rightPad']}px ({reach_ref['spanPct']}% width) vs. "
        f"rebuild L={reach_act['leftPad']}px R={reach_act['rightPad']}px ({reach_act['spanPct']}% width)"
    )
    for w in report["warnings"]:
        print(f"   ⚠ {w}")


def main():
    parser = argparse.ArgumentParser(
        description="Compare a reference screenshot against a local image or live URL with onion-skin overlay.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("reference", help="Path to reference screenshot PNG/JPG")
    parser.add_argument("target", help="Path to rebuild image OR live URL (http://...)")
    parser.add_argument("--output", "-o", default="./compare-diff.png", help="Output composite diff image path")
    parser.add_argument("--selector", default=None, help="CSS selector when target is a live URL")
    parser.add_argument("--scroll-y", type=int, default=None, help="Scroll Y offset (px) before capturing target URL")
    parser.add_argument("--delta-threshold", type=int, default=28, help="Per-pixel delta threshold (0-255) for magenta highlight")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Print JSON report to stdout")
    args = parser.parse_args()

    if not check_pillow():
        sys.exit(2)

    ref_path = Path(args.reference)
    if not ref_path.exists():
        print(f"Reference image not found: {ref_path}", file=sys.stderr)
        sys.exit(1)

    from PIL import Image
    with Image.open(ref_path) as ref_im:
        ref_size = ref_im.size

    if is_url(args.target):
        if not check_playwright():
            sys.exit(2)
        out_p = Path(args.output)
        actual_path = out_p.with_name(f"{out_p.stem}-actual.png")
        capture_target_url(args.target, ref_size, actual_path, selector=args.selector, scroll_y=args.scroll_y)
    else:
        actual_path = Path(args.target)
        if not actual_path.exists():
            print(f"Target image not found: {actual_path}", file=sys.stderr)
            sys.exit(1)

    report = compare_images(ref_path, actual_path, args.output, delta_threshold=args.delta_threshold)
    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        print(f"# Visual comparison: {ref_path.name} vs. {args.target}")
        print_compare_report(report)


if __name__ == "__main__":
    main()
