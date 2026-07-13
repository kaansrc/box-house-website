#!/usr/bin/env python3
"""Stage 1: pull Pages, Posts, and Media from the WordPress REST API.

Only published content is returned to unauthenticated requests, which is exactly
what we want. Output: raw/pages.json, raw/posts.json, raw/media.json.
"""
import sys

from common import BASE, RAW, get, make_session, save_json

PAGE_FIELDS = (
    "id,slug,link,title,content,excerpt,date,modified,"
    "featured_media,parent,menu_order,status,template"
)
MEDIA_FIELDS = (
    "id,slug,link,date,title,alt_text,caption,mime_type,"
    "source_url,media_details,post"
)

ENDPOINTS = {
    "pages": {"path": "/wp-json/wp/v2/pages", "fields": PAGE_FIELDS},
    "posts": {"path": "/wp-json/wp/v2/posts", "fields": PAGE_FIELDS},
    "media": {"path": "/wp-json/wp/v2/media", "fields": MEDIA_FIELDS},
}


def fetch_all(session, path, fields, per_page=100):
    """Page through a REST collection until exhausted, using X-WP-TotalPages."""
    items = []
    page = 1
    total_pages = 1
    while page <= total_pages:
        url = f"{BASE}{path}"
        r = get(session, url, params={"per_page": per_page, "page": page, "_fields": fields})
        if r.status_code == 400 and page > 1:
            # WP returns 400 "rest_post_invalid_page_number" past the last page.
            break
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        items.extend(batch)
        total_pages = int(r.headers.get("X-WP-TotalPages", total_pages))
        total = r.headers.get("X-WP-Total", "?")
        print(f"  {path}: page {page}/{total_pages}  (+{len(batch)}, total reported {total})")
        page += 1
    return items


def main():
    session = make_session()
    summary = {}
    for name, cfg in ENDPOINTS.items():
        print(f"Fetching {name} …")
        items = fetch_all(session, cfg["path"], cfg["fields"])
        out = RAW / f"{name}.json"
        save_json(out, items)
        summary[name] = len(items)
        print(f"  -> {len(items)} {name} saved to {out.relative_to(RAW.parent)}")
    print("\nDone:", ", ".join(f"{k}={v}" for k, v in summary.items()))
    # Sanity expectations from recon (warn, don't fail, if the site changed):
    expected = {"pages": 24, "media": 462}
    for k, v in expected.items():
        if summary.get(k) != v:
            print(f"  NOTE: expected ~{v} {k}, got {summary.get(k)} (site may have changed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
