#!/usr/bin/env python3
"""Stage 3: download every referenced image and build a manifest.

Image set = union of:
  - REST media source_urls (the 278 publicly-listed attachments, w/ alt+caption)
  - every /wp-content/uploads/ URL harvested from the 56 rendered HTML files
    (catches images on non-public rooms/offers that the media API hides)
For each harvested thumbnail (name-WxH.jpg) we also try the full-size original.

Output: assets/images/<YYYY/MM/file>, assets/media_manifest.json, assets/errors.log
"""
import re
import sys

from common import ASSETS, IMAGES, RAW, RAW_HTML, get, load_json, make_session, save_json
from extract_util import harvest_image_urls, uploads_relpath

THUMB_RE = re.compile(r"^(.*)-\d+x\d+(\.(?:jpe?g|png|gif|webp|svg))$", re.I)


def original_of(url):
    """name-970x647.jpg -> name.jpg (None if not a sized thumbnail)."""
    m = THUMB_RE.match(url)
    return m.group(1) + m.group(2) if m else None


def collect_urls():
    """Return (all_urls, meta_by_url) where meta comes from the media API."""
    meta = {}
    urls = set()
    for m in load_json(RAW / "media.json"):
        u = m.get("source_url")
        if not u:
            continue
        urls.add(u)
        md = m.get("media_details") or {}
        meta[u] = {
            "alt": m.get("alt_text") or "",
            "caption": re.sub(r"<[^>]+>", "", (m.get("caption") or {}).get("rendered", "")).strip(),
            "width": md.get("width"),
            "height": md.get("height"),
            "media_id": m.get("id"),
            "source": "media-api",
        }

    harvested = set()
    for html_file in sorted(RAW_HTML.rglob("*.html")):
        html = html_file.read_text(encoding="utf-8", errors="replace")
        harvested |= harvest_image_urls(html, "https://theboxhousehotel.com/")
    for u in harvested:
        if u not in meta:
            meta[u] = {"alt": "", "caption": "", "source": "harvested"}
        elif meta[u]["source"] == "media-api":
            meta[u]["source"] = "both"
    urls |= harvested

    # Also queue full-size originals behind thumbnails (best-effort).
    originals = set()
    for u in list(urls):
        o = original_of(u)
        if o and o not in urls:
            originals.add(o)
            meta.setdefault(o, {"alt": "", "caption": "", "source": "derived-original"})
    urls |= originals

    return sorted(urls), meta, len(harvested)


def download(session, url, errors):
    rel = uploads_relpath(url)
    dest = IMAGES / rel
    if dest.exists() and dest.stat().st_size > 0:
        return "cached", rel, dest.stat().st_size
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = get(session, url, stream=True)
    except Exception as e:  # network error
        errors.append(f"{url}\tEXC\t{e}")
        return "error", rel, 0
    if r.status_code != 200:
        errors.append(f"{url}\tHTTP {r.status_code}")
        return f"http{r.status_code}", rel, 0
    ctype = r.headers.get("Content-Type", "")
    if "image" not in ctype and not rel.lower().endswith((".svg",)):
        errors.append(f"{url}\tnot-image ({ctype})")
        return "not-image", rel, 0
    n = 0
    with open(dest, "wb") as f:
        for chunk in r.iter_content(65536):
            f.write(chunk)
            n += len(chunk)
    return "downloaded", rel, n


def main():
    session = make_session()
    urls, meta, n_harvested = collect_urls()
    print(f"Unique image URLs: {len(urls)}  (harvested from HTML: {n_harvested})")

    errors, manifest = [], []
    counts = {}
    for i, url in enumerate(urls, 1):
        status, rel, size = download(session, url, errors)
        counts[status] = counts.get(status, 0) + 1
        m = meta.get(url, {})
        manifest.append({
            "original_url": url,
            "local_path": f"assets/images/{rel}" if status in ("downloaded", "cached") else None,
            "status": status,
            "bytes": size,
            "source": m.get("source"),
            "alt": m.get("alt", ""),
            "caption": m.get("caption", ""),
            "width": m.get("width"),
            "height": m.get("height"),
        })
        if i % 50 == 0 or i == len(urls):
            print(f"  {i}/{len(urls)} … {counts}")

    save_json(ASSETS / "media_manifest.json", manifest)
    if errors:
        (ASSETS / "errors.log").write_text("\n".join(errors) + "\n", encoding="utf-8")

    got = counts.get("downloaded", 0) + counts.get("cached", 0)
    print(f"\nDone. images on disk: {got}   breakdown: {counts}")
    print(f"manifest: assets/media_manifest.json   errors: {len(errors)} (see assets/errors.log)")
    by_source = {}
    for m in manifest:
        if m["status"] in ("downloaded", "cached"):
            by_source[m["source"]] = by_source.get(m["source"], 0) + 1
    print("by source:", by_source)
    return 0


if __name__ == "__main__":
    sys.exit(main())
