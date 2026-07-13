#!/usr/bin/env python3
"""Stage 4: turn rendered HTML + REST metadata into Markdown + a master index.

For every content item (page/post/room/offer/portfolio):
  - metadata (title/slug/date/original_url) from REST where available, else HTML
  - body = main content region extracted from rendered HTML (REST bodies are hollow)
  - image URLs rewritten remote -> local assets/images/… paths
  - body HTML -> Markdown via pandoc
  - write content/<section>/<slug>.md (YAML frontmatter + Markdown)
    and content/<section>/<slug>.source.html (preserved raw content region)
Output: content/**/*.md, content/**/*.source.html, index.json
"""
import json
import re
import subprocess
import sys

from common import CONTENT, RAW, ROOT, load_json, save_json
from extract_util import (
    extract_main_content, harvest_image_urls, html_to_markdown_fallback,
    normalize_upload_url, uploads_relpath, visible_text_len,
)

# Match an uploads URL on either origin host, stopping at the file extension so it
# can't overrun into adjacent text (entity-encoded quotes, JSON blobs, etc.).
_UPLOAD_URL_RE = re.compile(
    r"https?://[^\s\"'“”‘’<>()\\,]*?/wp-content/uploads/[^\s\"'“”‘’<>()\\,]+?"
    r"\.(?:jpe?g|png|gif|webp|svg)",
    re.I,
)

SECTION = {  # sitemap type -> content/ subfolder
    "page": "pages", "post": "blog", "room": "rooms",
    "specialoffer": "offers", "portfolio_item": "portfolio",
    "portfolio_grid": "portfolio",
}


def rest_meta():
    """url -> {title, date, modified, featured_media, content_html, ...} from REST."""
    out = {}
    for name in ("pages", "posts"):
        for p in load_json(RAW / f"{name}.json"):
            out[p["link"].rstrip("/")] = {
                "title": re.sub(r"<[^>]+>", "", p["title"]["rendered"]).strip(),
                "date": p.get("date"),
                "modified": p.get("modified"),
                "featured_media": p.get("featured_media"),
                "content_html": (p.get("content") or {}).get("rendered", ""),
                "rest_excerpt": re.sub(r"<[^>]+>", "", (p.get("excerpt") or {}).get("rendered", "")).strip(),
            }
    return out


def prose_len(html):
    """Length of visible text in an HTML fragment (for source comparison)."""
    if not html:
        return 0
    from bs4 import BeautifulSoup
    s = BeautifulSoup(html, "lxml")
    for t in s(["script", "style", "noscript"]):
        t.extract()
    return len(re.sub(r"\s+", " ", s.get_text(" ")).strip())


def featured_url(media_id, media_index):
    return media_index.get(media_id)


def html_to_markdown(html):
    """Prefer pandoc; fall back to the resilient walker when pandoc loses content.

    Pandoc silently drops most text on this theme's malformed carousel markup, so
    if its output preserves <50% of the source's visible text, use the fallback.
    """
    src_len = visible_text_len(html)
    r = subprocess.run(
        ["pandoc", "-f", "html", "-t", "gfm-raw_html", "--wrap=none"],
        input=html.encode("utf-8"), capture_output=True,
    )
    md = r.stdout.decode("utf-8") if r.returncode == 0 else ""
    md_text = len(re.sub(r"\s+", " ", re.sub(r"[#>*!\[\]()`_-]", " ", md)).strip())
    if r.returncode != 0 or (src_len > 80 and md_text < 0.5 * src_len):
        return html_to_markdown_fallback(html)
    return md


def rewrite_local(text):
    """Rewrite any uploads URL (either origin host) in `text` to its local path.

    Run on pandoc's Markdown output, where entities are already decoded to real
    characters (curly quotes, ×); the delimiter class + normalize handle the rest.
    """
    def repl(m):
        return "/assets/images/" + uploads_relpath(normalize_upload_url(m.group(0)))
    return _UPLOAD_URL_RE.sub(repl, text)


def yaml_frontmatter(d):
    lines = ["---"]
    for k, v in d.items():
        if v is None or v == "":
            continue
        if isinstance(v, list):
            lines.append(f"{k}:")
            for item in v:
                lines.append(f"  - {json.dumps(item, ensure_ascii=False)}")
        else:
            lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    lines.append("---\n")
    return "\n".join(lines)


def main():
    items = load_json(RAW / "html_index.json")
    meta = rest_meta()
    media_index = {m["id"]: m["source_url"] for m in load_json(RAW / "media.json")}

    index = []
    for it in items:
        if not it.get("ok"):
            continue
        html_path = ROOT / it["file"]
        html = html_path.read_text(encoding="utf-8", errors="replace")
        content_html, html_title = extract_main_content(html, it["url"])

        rm = meta.get(it["url"].rstrip("/"), {})
        title = rm.get("title") or html_title or it["slug"]
        images = sorted(harvest_image_urls(html, it["url"]))
        local_images = ["/assets/images/" + uploads_relpath(u) for u in images]
        feat = featured_url(rm.get("featured_media", 0), media_index)

        # Pick the richer body source: clean REST content vs rendered extraction.
        rest_html = rm.get("content_html", "")
        if prose_len(rest_html) >= prose_len(content_html):
            body_html, body_source = rest_html, "rest"
        else:
            body_html, body_source = content_html, "rendered"

        section = SECTION.get(it["type"], "misc")
        out_dir = CONTENT / section
        out_dir.mkdir(parents=True, exist_ok=True)

        # Preserve the chosen raw body (faithful original), then convert to Markdown
        # and localize image URLs once on pandoc's decoded output.
        (out_dir / f"{it['slug']}.source.html").write_text(body_html, encoding="utf-8")
        md_body = rewrite_local(html_to_markdown(body_html))

        fm = yaml_frontmatter({
            "title": title,
            "slug": it["slug"],
            "type": it["type"],
            "original_url": it["url"],
            "date": rm.get("date"),
            "modified": rm.get("modified"),
            "featured_image": ("/assets/images/" + uploads_relpath(feat)) if feat else None,
            "excerpt": rm.get("rest_excerpt"),
            "body_source": body_source,
            "images": local_images,
            "source_html": f"content/{section}/{it['slug']}.source.html",
        })
        (out_dir / f"{it['slug']}.md").write_text(fm + md_body.strip() + "\n", encoding="utf-8")

        index.append({
            "title": title, "slug": it["slug"], "type": it["type"], "section": section,
            "original_url": it["url"], "markdown": f"content/{section}/{it['slug']}.md",
            "featured_image": ("/assets/images/" + uploads_relpath(feat)) if feat else None,
            "image_count": len(local_images), "images": local_images,
        })
        print(f"  ✓ {section:10}/{it['slug']:38} imgs={len(local_images):3d}  '{title[:40]}'")

    save_json(ROOT / "index.json", {
        "site": "theboxhousehotel.com",
        "generated_from": "WordPress REST API + rendered HTML",
        "count": len(index),
        "items": index,
    })
    print(f"\nDone: {len(index)} content files -> content/  |  index.json written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
