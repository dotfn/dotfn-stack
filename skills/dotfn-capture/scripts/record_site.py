#!/usr/bin/env python3
"""
record_site.py — Record a site top-to-bottom and pull out the frames where
something actually changed (on-demand, needs ffmpeg for frame extraction)

Every other capture technique in this skill works by diffing two states: resting
vs. forced-hover, before-scroll vs. after-scroll. That's blind to anything that
isn't reducible to two snapshots — a mount animation that plays once before any
probe starts measuring, a skeleton that only resolves once a fetch comes back,
a counter that ticks up over a few seconds, an ambient loop (a pulsing dot, a
drifting blob) that never settles into a single "after" state at all.

This script records the real thing instead of diffing it: Playwright starts
recording *before* navigation (so a mount animation is on tape, not finished
before the first probe runs), scrolls the page top to bottom at a human pace so
scroll-linked and IntersectionObserver motion plays out for real, then holds
at the bottom for a settle period so fetch-delayed and looping effects get a
chance to fire. ffmpeg then pulls out only the frames where the picture
actually changed, not a uniform grid of mostly-identical frames — two
techniques, in order: scene-change detection first (finds the exact *moment*
something happened, with a real timestamp — a mount animation firing, a toast
appearing), and mpdecimate second, only if the first finds nothing (catches
*gradual* continuous motion — a slow drift, a scroll-through — that never
produces a single frame-to-frame jump sharp enough for scene detection to
notice). Reading the output never means reading forty near-duplicates.

Basic usage:
    python record_site.py https://example.com

Longer settle, for a site with a delayed fetch or a slow loop:
    python record_site.py https://example.com --settle 10

Watch one already-visible interaction without scrolling away from it:
    python record_site.py https://example.com --no-scroll --settle 8

Just the video, skip frame extraction (e.g. no ffmpeg available):
    python record_site.py https://example.com --no-extract-frames

Requirements:
    pip install playwright
    playwright install chromium
    ffmpeg on PATH (frame extraction only — the recording itself needs only Playwright)
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

VIEWPORT_PRESETS = {"desktop": (1440, 900), "tablet": (768, 1024), "mobile": (375, 812)}
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
COOKIE_ACCEPT_SELECTORS = [
    'button[id*="accept" i]', 'button[id*="agree" i]', 'button[id*="consent" i]',
    'button[class*="accept" i]', 'button[aria-label*="accept" i]', '[data-testid*="accept" i]',
    '#onetrust-accept-btn-handler', '.cc-accept', '.cc-allow', '.cookie-accept', '.gdpr-accept',
]


def check_playwright_installed():
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        print(
            "Playwright is not installed.\n\nInstall with:\n\n"
            "    pip install playwright\n    playwright install chromium\n",
            file=sys.stderr,
        )
        return False


def check_ffmpeg_installed():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def parse_viewport(s):
    if s in VIEWPORT_PRESETS:
        return VIEWPORT_PRESETS[s]
    try:
        w, h = s.lower().split("x")
        return int(w), int(h)
    except Exception:
        raise argparse.ArgumentTypeError(f"Invalid viewport: {s}")


def dismiss_cookie_banner(page):
    for selector in COOKIE_ACCEPT_SELECTORS:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0 and locator.is_visible(timeout=500):
                locator.click(timeout=1000)
                page.wait_for_timeout(500)
                return True
        except Exception:
            continue
    return False


def record(url, output_path, viewport, *, scroll, scroll_duration, settle,
           dismiss_cookies, user_agent, wait_until, timeout):
    from playwright.sync_api import sync_playwright

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    video_dir = output_path.parent / f".{output_path.stem}-video-tmp"
    video_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # record_video_dir is set on the CONTEXT, before any page exists — recording
        # starts here, which is what puts a mount animation on tape instead of letting
        # it finish before the first frame is ever captured.
        context = browser.new_context(
            viewport={"width": viewport[0], "height": viewport[1]},
            record_video_dir=str(video_dir),
            record_video_size={"width": viewport[0], "height": viewport[1]},
            user_agent=user_agent,
        )
        page = context.new_page()
        print(f"Recording {url}  ({viewport[0]}x{viewport[1]})")

        try:
            page.goto(url, wait_until=wait_until, timeout=timeout)
        except Exception as e:
            print(f"   Page took longer than expected: {e}. Continuing with what rendered.")

        if dismiss_cookies:
            dismiss_cookie_banner(page)

        page.wait_for_timeout(400)

        if scroll:
            try:
                height = page.evaluate("document.documentElement.scrollHeight")
            except Exception:
                height = viewport[1]
            max_scroll = max(0, height - viewport[1])
            if max_scroll > 0:
                steps = 36
                step_pause = max(20, int(scroll_duration * 1000 / steps))
                print(f"   Scrolling top to bottom over ~{scroll_duration}s ({max_scroll}px)...")
                for i in range(steps + 1):
                    top = round(max_scroll * i / steps)
                    page.evaluate(f"window.scrollTo(0, {top})")
                    page.wait_for_timeout(step_pause)
            else:
                print("   Page fits one viewport — nothing to scroll through.")

        if settle > 0:
            print(f"   Holding for {settle}s (catches delayed, fetch-driven, and looping effects)...")
            page.wait_for_timeout(settle * 1000)

        context.close()
        browser.close()

    recorded = list(video_dir.glob("*.webm"))
    if not recorded:
        print("   No video file was produced.", file=sys.stderr)
        return None
    recorded[0].replace(output_path)
    try:
        video_dir.rmdir()
    except OSError:
        pass
    return output_path


def probe_duration(video_path):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video_path)],
            capture_output=True, text=True, check=True,
        )
        return float(out.stdout.strip())
    except Exception:
        return None


def extract_change_frames(video_path, out_dir, scene_threshold, max_frames, mpdecimate_sensitivity, fallback_fps):
    """Two change-detection techniques, in order, because they catch different
    things and neither alone is enough:

    1. **Scene-change detection** (ffmpeg's `scene` score) finds the *moment*
       something happened — a mount animation firing, a fetch resolving, a toast
       appearing. It's built for sharp frame-to-frame jumps and gives a real
       timestamp for each one, which is exactly what you want for "when did this
       fire" questions. It's blind to slow, continuous change, though — a blob
       drifting or a page scrolling steadily produces no single jump big enough
       to register, so a pure scroll-through can come back with zero hits even
       though the whole video is clearly moving.
    2. **mpdecimate** (a frame-deduplication filter, not a scene detector) drops
       frames that are near-duplicates of the one before them — what survives is
       a representative sample across exactly that continuous motion scene-change
       misses. It doesn't carry real timestamps the same way (frames are
       renumbered on output), so it's the second choice, not the first.

    `-fps_mode vfr` (not the older `-vsync vfr`, removed in modern ffmpeg builds —
    this one cost real debugging time to track down) is required for both: without
    it the muxer tries to write one PNG per *input* frame regardless of selection,
    silently discarding the whole point of filtering frames out."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in out_dir.glob("*.png"):
        f.unlink()

    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", f"select='gt(scene,{scene_threshold})',showinfo",
        "-fps_mode", "vfr", "-frames:v", str(max_frames),
        str(out_dir / "change-%03d.png"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    times = [float(t) for t in re.findall(r"pts_time:([\d.]+)", result.stderr)]
    frames = sorted(out_dir.glob("change-*.png"))
    if frames:
        return list(zip(frames, times)) if len(times) == len(frames) else [(f, None) for f in frames]

    # Scene detection found no sharp jumps — try mpdecimate for gradual,
    # continuous motion (a scroll-through, a slow drift) instead of giving up.
    print(f"   No sharp scene changes above threshold {scene_threshold} — trying mpdecimate for gradual motion...")
    hi = round(300 + mpdecimate_sensitivity * 1800)
    lo = round(hi * 0.5)
    cmd2 = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", f"mpdecimate=hi={hi}:lo={lo}:frac=0.2",
        "-fps_mode", "vfr", "-frames:v", str(max_frames),
        str(out_dir / "decimate-%03d.png"),
    ]
    subprocess.run(cmd2, capture_output=True, text=True)
    frames = sorted(out_dir.glob("decimate-*.png"))
    if frames:
        return [(f, None) for f in frames]

    # Truly static, or both filters failed for some other reason — uniform
    # sampling at least returns something instead of nothing.
    print(f"   mpdecimate found nothing either — falling back to {fallback_fps}fps uniform sampling.")
    cmd3 = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", f"fps={fallback_fps}", "-frames:v", str(max_frames),
        str(out_dir / "frame-%03d.png"),
    ]
    subprocess.run(cmd3, capture_output=True, text=True)
    frames = sorted(out_dir.glob("frame-*.png"))
    return [(f, None) for f in frames]


def main():
    parser = argparse.ArgumentParser(
        description="Record a site top-to-bottom and extract the frames where something changed.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__,
    )
    parser.add_argument("url")
    parser.add_argument("--output", "-o", default="./recording.webm")
    parser.add_argument("--viewport", type=parse_viewport, default=VIEWPORT_PRESETS["desktop"])
    parser.add_argument("--scroll", dest="scroll", action="store_true", default=True)
    parser.add_argument("--no-scroll", dest="scroll", action="store_false",
                         help="Stay on the initial view instead of scrolling — for watching one "
                              "already-visible interaction (a loop, a delayed fetch) over time.")
    parser.add_argument("--scroll-duration", type=float, default=6.0, help="Seconds to spend scrolling top to bottom (default: 6).")
    parser.add_argument("--settle", type=float, default=4.0,
                         help="Seconds to hold still after scrolling (or from the start, with --no-scroll) "
                              "before stopping — this is what catches fetch-delayed and looping effects (default: 4).")
    parser.add_argument("--no-dismiss-cookies", dest="dismiss_cookies", action="store_false", default=True)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--wait-until", choices=["load", "domcontentloaded", "networkidle"], default="networkidle")
    parser.add_argument("--timeout", type=int, default=30000)
    parser.add_argument("--extract-frames", dest="extract_frames", action="store_true", default=True)
    parser.add_argument("--no-extract-frames", dest="extract_frames", action="store_false")
    parser.add_argument("--frames-out", default=None, help="Folder for extracted frames (default: <output-stem>-frames/).")
    parser.add_argument("--scene-threshold", type=float, default=0.015,
                         help="Sharp-jump sensitivity, 0-1, lower = more frames (default: 0.015). "
                              "Finds discrete moments (a mount animation, a fetch resolving) with a real timestamp.")
    parser.add_argument("--mpdecimate-sensitivity", type=float, default=0.3,
                         help="Gradual-motion sensitivity, 0-1, lower = more frames (default: 0.3). "
                              "Used only when scene detection finds nothing — catches a drift or scroll-through instead.")
    parser.add_argument("--max-frames", type=int, default=20, help="Cap on extracted frames (default: 20).")
    parser.add_argument("--fallback-fps", type=float, default=0.5,
                         help="Uniform sampling rate used only if scene detection finds nothing (default: 0.5 = one frame per 2s).")
    args = parser.parse_args()

    if not check_playwright_installed():
        sys.exit(2)

    output_path = Path(args.output)
    try:
        video_path = record(
            args.url, output_path, args.viewport,
            scroll=args.scroll, scroll_duration=args.scroll_duration, settle=args.settle,
            dismiss_cookies=args.dismiss_cookies, user_agent=args.user_agent,
            wait_until=args.wait_until, timeout=args.timeout,
        )
    except Exception as e:
        print(f"Error during recording: {e}", file=sys.stderr)
        sys.exit(1)

    if video_path is None:
        sys.exit(1)

    duration = probe_duration(video_path)
    size_kb = video_path.stat().st_size // 1024
    print(f"   Video saved: {video_path} ({size_kb} KB{f', {duration:.1f}s' if duration else ''})")

    if not args.extract_frames:
        return

    if not check_ffmpeg_installed():
        print(
            "\nffmpeg is not installed — the video is saved, but frame extraction needs it.\n"
            "Install with:\n    brew install ffmpeg        # macOS\n    apt install ffmpeg         # Debian/Ubuntu\n"
            "Then re-run with the same --output to extract frames from the existing video:\n"
            f"    python record_site.py {args.url} --output {video_path} --extract-frames\n",
            file=sys.stderr,
        )
        sys.exit(2)

    frames_out = args.frames_out or f"{video_path.stem}-frames"
    print(f"   Extracting changed frames to {frames_out}/ (scene threshold {args.scene_threshold})...")
    paired = extract_change_frames(
        video_path, frames_out, args.scene_threshold, args.max_frames,
        args.mpdecimate_sensitivity, args.fallback_fps,
    )

    if not paired:
        print("   No frames extracted — the recording may be static, or ffmpeg failed. Check the video directly.")
        return

    print(f"   {len(paired)} frame(s) — read only the ones relevant to what you're looking for, not all of them:")
    for path, t in paired:
        when = f"~{t:.1f}s" if t is not None else "(timestamp unavailable — uniform fallback)"
        print(f"     {path}  {when}")


if __name__ == "__main__":
    main()
