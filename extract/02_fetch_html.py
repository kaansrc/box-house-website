#!/usr/bin/env python3
"""Stage 2: fetch rendered front-end HTML for every content URL.

REST bodies are hollow for this page-builder theme, so the rendered HTML is the
source of truth for body content and (lazy-loaded) images. URL list =
  - page + post URLs from the REST dumps (raw/pages.json, raw/posts.json)
  - custom-post-type URLs from the sitemap (room, specialoffer, portfolio_item,
    portfolio_grid) — these aren't in REST at all.

Output: raw/html/<type>/<slug>.html  and  raw/html_index.json
"""
import re
import sys
from urllib.parse import urlparse

from common import BASE, RAW, RAW_HTML, get, load_json, make_session, save_json

CPT_SITEMAPS = {
    "room": "/wp-sitemap-posts-room-1.xml",
    "specialoffer": "/wp-sitemap-posts-specialoffer-1.xml",
    "portfolio_item": "/wp-sitemap-posts-portfolio_item-1.xml",
    "portfolio_grid": "/wp-sitemap-posts-portfolio_grid-1.xml",
}
LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)


def slug_from_url(url):
    parts = [p for p in urlparse(url).path.split("/") if p]
    return parts[-1] if parts else "index"


def sitemap_urls(session, path):
    # Sitemaps are simple; parse <loc> with regex to avoid XML-parser XXE surface.
    r = get(session, BASE + path)
    if r.status_code != 200:
        print(f"  ! {path} -> HTTP {r.status_code} (skipping)")
        return []
    return [u.strip() for u in LOC_RE.findall(r.text)]


def build_url_list(session):
    """Return list of {type, slug, url} for every content URL to fetch."""
    items = []
    seen = set()

    def add(kind, url, slug=None):
        url = url.split("#")[0]
        if url in seen:
            return
        seen.add(url)
        items.append({"type": kind, "slug": slug or slug_from_url(url), "url": url})

    for p in load_json(RAW / "pages.json"):
        add("page", p["link"], p["slug"])
    for p in load_json(RAW / "posts.json"):
        add("post", p["link"], p["slug"])
    for kind, path in CPT_SITEMAPS.items():
        for url in sitemap_urls(session, path):
            add(kind, url)
    return items


def main():
    session = make_session()
    items = build_url_list(session)
    print(f"URLs to fetch: {len(items)}")
    by_type = {}
    for it in items:
        by_type[it["type"]] = by_type.get(it["type"], 0) + 1
    print("  by type:", by_type)

    ok, fail = 0, 0
    for it in items:
        r = get(session, it["url"])
        if r.status_code != 200 or not r.text:
            print(f"  ! {it['url']} -> HTTP {r.status_code}")
            it["ok"] = False
            fail += 1
            continue
        out_dir = RAW_HTML / it["type"]
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{it['slug']}.html"
        out.write_text(r.text, encoding="utf-8")
        it["file"] = str(out.relative_to(RAW.parent))
        it["ok"] = True
        it["bytes"] = len(r.text)
        ok += 1
        print(f"  ✓ {it['type']:14} {it['slug']:36} {len(r.text):7d} B")

    save_json(RAW / "html_index.json", items)
    print(f"\nDone: {ok} fetched, {fail} failed -> raw/html_index.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
