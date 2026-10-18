#!/usr/bin/env python3
"""
extract_tokens.py — CSS custom properties and @keyframes from a URL

Fetches a page's HTML, every linked stylesheet, and every inline <style>
block, then extracts:

  - every `--name: value;` custom property definition
  - every `@keyframes name { ... }` block, verbatim

Custom properties are grouped by a heuristic category (color / spacing /
typography / radius / shadow / duration / breakpoint / other), var() aliases
are resolved, framework-internal noise is dropped, and the result is printed
as a digest capped at --budget characters. The full data is written to disk;
--search queries that saved file without refetching anything.

Stdlib only. No pip install required.

Usage:
    python extract_tokens.py https://example.com
    python extract_tokens.py https://example.com --output ./tokens.json
    python extract_tokens.py --search 'radius|shadow'
    python extract_tokens.py --search 'pulse' --kind animation
    python extract_tokens.py https://example.com --json
"""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urljoin, urlparse

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

CSS_VAR_RE = re.compile(
    r"(?:(?<=[{;\s])|^)--([A-Za-z0-9_-]+)\s*:\s*([^;}]+?)\s*(?:!important\s*)?(?:;|(?=\}))",
    re.DOTALL,
)
LINK_TAG_RE = re.compile(r'<link\s+[^>]*rel=["\']?stylesheet["\']?[^>]*>', re.IGNORECASE)
HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
STYLE_BLOCK_RE = re.compile(r"<style\b[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
KEYFRAMES_START_RE = re.compile(r"@(?:-webkit-|-moz-|-o-)?keyframes\s+([A-Za-z0-9_-]+)\s*\{")

CATEGORY_HINTS = [
    ("color", ("color", "bg", "background", "border", "fg", "foreground", "surface", "text",
               "accent", "primary", "secondary", "muted", "success", "warning", "error", "danger")),
    ("spacing", ("space", "spacing", "gap", "padding", "margin", "inset", "size")),
    ("typography", ("font", "text", "leading", "tracking", "line-height", "letter-spacing", "weight")),
    ("radius", ("radius", "rounded")),
    ("shadow", ("shadow", "elevation")),
    ("duration", ("duration", "transition", "delay", "ease")),
    ("breakpoint", ("breakpoint", "screen", "viewport")),
]
NOISE_PREFIXES = ("tw-", "shiki", "radix-", "chakra-", "mantine-", "swiper-", "toastify-",
                   "rdp-", "framer-", "animate-", "webkit-", "moz-", "docsearch-", "cf-")
VAR_REF_RE = re.compile(r"^var\(\s*--([A-Za-z0-9_-]+)\s*(?:,\s*(.+))?\)$")
DIGEST_SHARES = (("color", 0.34), ("typography", 0.18), ("spacing", 0.14), ("radius", 0.08),
                  ("shadow", 0.10), ("duration", 0.06), ("breakpoint", 0.04), ("other", 0.06))


def http_get(url, timeout=15):
    req = urlrequest.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
    except (urlerror.URLError, urlerror.HTTPError, TimeoutError, OSError) as e:
        print(f"   warn: failed to fetch {url}: {e}", file=sys.stderr)
        return None


def find_stylesheet_urls(html, base_url):
    urls = []
    for tag in LINK_TAG_RE.findall(html):
        m = HREF_RE.search(tag)
        if not m:
            continue
        href = m.group(1).strip()
        if href.startswith(("data:", "javascript:", "#")):
            continue
        urls.append(urljoin(base_url, href))
    return urls


def extract_vars(css_text):
    return [(name, " ".join(v.split())) for name, v in CSS_VAR_RE.findall(css_text)]


def extract_keyframes(css_text):
    """Find every @keyframes block and return (name, body) with balanced braces."""
    blocks = []
    for m in KEYFRAMES_START_RE.finditer(css_text):
        name = m.group(1)
        depth = 1
        i = m.end()
        start = i
        while i < len(css_text) and depth > 0:
            if css_text[i] == "{":
                depth += 1
            elif css_text[i] == "}":
                depth -= 1
            i += 1
        body = css_text[start:i - 1].strip()
        blocks.append((name, " ".join(body.split())))
    return blocks


def categorize(name):
    lower = name.lower()
    for category, hints in CATEGORY_HINTS:
        if any(h in lower for h in hints):
            return category
    return "other"


def is_noise(name, value):
    if name.lower().startswith(NOISE_PREFIXES):
        return True
    return len(value) > 90 or value in ("initial", "inherit", "unset", "")


def resolve_alias(value, table, depth=0):
    m = VAR_REF_RE.match(value.strip())
    if not m or depth > 6:
        return value
    target = table.get(m.group(1))
    if target is None:
        return m.group(2) or value
    return resolve_alias(target, table, depth + 1)


def merge_uniq(pairs):
    seen, overrides = {}, {}
    for name, value in pairs:
        if name not in seen:
            seen[name] = value
        elif seen[name] != value:
            overrides.setdefault(name, []).append(value)
    return seen, overrides


def build_digest(seen, overrides, keyframes, url, sources, budget):
    kept = {n: v for n, v in seen.items() if not is_noise(n, v)}
    by_category = {}
    for name, value in kept.items():
        resolved = resolve_alias(value, seen)
        by_category.setdefault(categorize(name), {})[name] = resolved

    out = [
        f"# Tokens and animation: {url}",
        f"{len(seen)} custom properties, {len(keyframes)} @keyframes block(s), "
        f"{len(sources)} stylesheet source(s). {len(seen) - len(kept)} framework/noise vars hidden. "
        f"Full data saved; use --search 'pattern' to look up more without refetching.",
    ]
    carry = 0
    for category, share in DIGEST_SHARES:
        items = by_category.get(category)
        allowance = int(budget * share) + carry
        if not items:
            carry = allowance
            continue
        lines = [f"- --{n}: {v}" for n, v in sorted(items.items())]
        out.append(f"\n## {category} ({len(items)})")
        used = 0
        for i, line in enumerate(lines):
            if used + len(line) + 1 > allowance:
                out.append(f"- (+{len(lines) - i} more — use --search)")
                break
            out.append(line)
            used += len(line) + 1
        carry = max(0, allowance - used)

    if keyframes:
        out.append(f"\n## animation ({len(keyframes)})")
        for name, body in keyframes[:12]:
            short = body if len(body) <= 160 else body[:157] + "..."
            out.append(f"- @keyframes {name}: {short}")
        if len(keyframes) > 12:
            out.append(f"- (+{len(keyframes) - 12} more — use --search --kind animation)")
    else:
        out.append("\n## animation (0)\nNo @keyframes found in any fetched stylesheet.")

    return "\n".join(out)


def search_saved(path, pattern, kind, budget):
    p = Path(path)
    if not p.exists():
        return f"{p} not found. Run with a URL first."
    data = json.loads(p.read_text(encoding="utf-8"))
    regex = re.compile(pattern, re.IGNORECASE)
    lines, used = [], 0

    def emit(line):
        nonlocal used
        if used + len(line) > budget:
            return False
        lines.append(line)
        used += len(line) + 1
        return True

    if kind in ("all", "token"):
        seen = {n: i["value"] for cat in data.get("tokens", {}).values() for n, i in cat.items()}
        for name, value in seen.items():
            if regex.search(name) or regex.search(value):
                if not emit(f"--{name}: {resolve_alias(value, seen)}"):
                    break
    if kind in ("all", "animation"):
        for item in data.get("animations", []):
            if regex.search(item["name"]) or regex.search(item["body"]):
                if not emit(f"@keyframes {item['name']}: {item['body'][:160]}"):
                    break
    return "\n".join(lines) if lines else f"No match for /{pattern}/ in {p}."


def main():
    parser = argparse.ArgumentParser(
        description="Extract CSS custom properties and @keyframes from a URL. Stdlib only.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("url", nargs="?", help="URL of the page to inspect")
    parser.add_argument("--search", metavar="REGEX", default=None,
                         help="Search the file saved by a previous run — no network.")
    parser.add_argument("--kind", choices=["all", "token", "animation"], default="all",
                         help="Narrow --search to custom properties, @keyframes, or both (default).")
    parser.add_argument("--output", "-o", default="./tokens.json", help="Full JSON path.")
    parser.add_argument("--budget", type=int, default=6000, help="Max digest characters (default: 6000).")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Print full JSON, not the digest.")
    parser.add_argument("--timeout", type=int, default=15)
    args = parser.parse_args()

    if args.search:
        print(search_saved(args.output, args.search, args.kind, args.budget))
        return
    if not args.url:
        parser.error("a URL is required unless --search is given")
    if not urlparse(args.url).scheme:
        print("URL must include a scheme (http:// or https://)", file=sys.stderr)
        sys.exit(2)

    html = http_get(args.url, timeout=args.timeout)
    if html is None:
        print("Could not fetch the page. Aborting.", file=sys.stderr)
        sys.exit(1)

    all_pairs, all_keyframes, sources = [], [], []

    for i, css in enumerate(STYLE_BLOCK_RE.findall(html)):
        pairs, kf = extract_vars(css), extract_keyframes(css)
        if pairs or kf:
            sources.append(f"inline-style-{i}")
            all_pairs.extend(pairs)
            all_keyframes.extend(kf)

    stylesheet_urls = find_stylesheet_urls(html, args.url)
    print(f"Found {len(stylesheet_urls)} linked stylesheet(s).", file=sys.stderr)
    for ss_url in stylesheet_urls:
        css_text = http_get(ss_url, timeout=args.timeout)
        if css_text is None:
            continue
        pairs, kf = extract_vars(css_text), extract_keyframes(css_text)
        if pairs or kf:
            sources.append(ss_url)
            all_pairs.extend(pairs)
            all_keyframes.extend(kf)

    seen, overrides = merge_uniq(all_pairs)
    keyframes_uniq = list({name: body for name, body in all_keyframes}.items())

    output = {
        "tokens": {},
        "animations": [{"name": n, "body": b} for n, b in keyframes_uniq],
        "_meta": {"source_url": args.url, "stylesheet_count": len(sources), "stylesheets": sources},
    }
    for name, value in seen.items():
        cat = categorize(name)
        entry = {"value": value, "source": "css-custom-property"}
        if name in overrides:
            entry["alternatives"] = overrides[name]
        output["tokens"].setdefault(cat, {})[name] = entry

    serialized = json.dumps(output, indent=None, ensure_ascii=False)
    if args.as_json:
        print(serialized)
        return

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(serialized, encoding="utf-8")
    print(build_digest(seen, overrides, keyframes_uniq, args.url, sources, args.budget))


if __name__ == "__main__":
    main()
