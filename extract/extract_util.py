"""Shared HTML utilities: harvest image URLs and isolate a page's main content.

This theme is a page builder that stores layout in post-meta, so the REST body is
often empty. The real content + images live in the rendered front-end HTML, where
images are lazy-loaded via `data-src` (not `src`). We harvest from every attribute
that can carry an uploads URL.
"""
import html as html_lib
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Comment, NavigableString

# Text nodes that are actually leaked code/markup or structural comment residue.
_CODE_TEXT_RE = re.compile(
    r"<script|<style|<div\b|google\.maps|gmap_canvas|function\s+\w+\s*\(|"
    r"^\s*/[.#]|mapTypeId|addListener",
    re.I,
)


def _is_junk_img(src):
    return (not src) or src.startswith("data:")

# Delimiter class excludes whitespace, straight + curly quotes, angle brackets,
# parens, backslash and comma — so a match can't run across adjacent URLs even
# inside entity-encoded JSON blobs. Match stops AT the file extension (non-greedy).
_STOP = r"[^\s\"'“”‘’<>()\\,]"
UPLOADS_RE = re.compile(
    rf"https?://{_STOP}*?/wp-content/uploads/{_STOP}+?\.(?:jpe?g|png|gif|webp|svg)",
    re.I,
)
IMG_EXT_RE = re.compile(r"\.(?:jpe?g|png|gif|webp|svg)(?:\?.*)?$", re.I)


def normalize_upload_url(u):
    """Undo WP texturize (×→x in dimensions) and drop query/fragment."""
    if not u:
        return u
    u = u.replace("×", "x")            # 970×566 -> 970x566
    u = u.split("?")[0].split("#")[0]
    return u

# Attributes (across the theme + lazy-load libs) that may hold an image URL.
IMG_ATTRS = [
    "src", "data-src", "data-lazy-src", "data-original", "data-lazy",
    "data-bg", "data-background", "data-thumb", "data-large_image",
]
SRCSET_ATTRS = ["srcset", "data-srcset", "data-lazy-srcset"]

# Selectors tried in order to find the main content region of a rendered page.
CONTENT_SELECTORS = [
    "div.entry-content", "div.page-content", "article .post-content",
    "div.content-area", "main", "div#content", "div#primary",
    "article", "div.site-content", "div.container-fluid",
]
# Chrome + interactive widgets to strip. Widgets (booking form, JS store-locator,
# contact form, CAPTCHA) carry no reusable text and otherwise dominate extraction.
STRIP_SELECTORS = [
    "script", "style", "noscript", "link", "svg",
    "nav", "#main-nav", "#masthead", "#colophon",
    ".site-header", ".site-footer", ".main-navigation", "#site-navigation",
    ".widget-area", ".sidebar", ".breadcrumb", ".breadcrumbs",
    ".cookie-notice", "#cookie-notice", "#wpadminbar",
    # interactive widgets — no reusable prose
    "#booknow", ".booking-form", ".book-now",
    ".asl-storelocator", "#asl-storelocator", '[id^="asl-"]',
    '[class*="storelocator"]', '[class*="store-locator"]', '[class*="cetabo"]',
    ".wpcf7", "form", ".captcha", ".g-recaptcha",
]


def _clean_url(u):
    if not u:
        return None
    u = u.strip().strip('"\'')
    # background-image:url(...) leftovers
    u = u.strip("()")
    return u or None


def harvest_image_urls(html, base_url):
    """Return a set of absolute /wp-content/uploads/ image URLs referenced in `html`."""
    # Decode entities first: the theme embeds a plugin-config JSON that uses
    # &#8221; for quotes and &#215; for ×, which otherwise defeats URL delimiting.
    text = html_lib.unescape(html)
    urls = set()

    # 1) Fast regex pass over the (decoded) HTML — catches inline styles, JSON, srcset.
    for m in UPLOADS_RE.findall(text):
        urls.add(m)

    # 2) DOM pass for attribute values that may be relative.
    soup = BeautifulSoup(html, "lxml")  # BS4 decodes entities in attribute values
    for tag in soup.find_all(True):
        for attr in IMG_ATTRS:
            v = _clean_url(tag.get(attr))
            if v and "/wp-content/uploads/" in v:
                urls.add(urljoin(base_url, v))
        for attr in SRCSET_ATTRS:
            v = tag.get(attr)
            if v:
                for part in v.split(","):
                    cand = _clean_url(part.strip().split(" ")[0])
                    if cand and "/wp-content/uploads/" in cand:
                        urls.add(urljoin(base_url, cand))
        style = tag.get("style") or ""
        for m in re.findall(r"url\(([^)]+)\)", style):
            cand = _clean_url(m)
            if cand and "/wp-content/uploads/" in cand:
                urls.add(urljoin(base_url, cand))

    # Normalize + keep only real image URLs.
    out = set()
    for u in urls:
        u = normalize_upload_url(u)
        if IMG_EXT_RE.search(u) and "/wp-content/uploads/" in u:
            out.add(u)
    return out


def uploads_relpath(url):
    """Map an uploads URL to its repo-local path, preserving the YYYY/MM structure.

    https://…/wp-content/uploads/2019/03/Box-House.jpg -> 2019/03/Box-House.jpg
    """
    path = urlparse(url).path
    marker = "/wp-content/uploads/"
    i = path.find(marker)
    rel = path[i + len(marker):] if i >= 0 else path.lstrip("/")
    return rel


def extract_main_content(html, base_url):
    """Return (content_html, plain_title) for the main content region.

    Falls back to <body> minus chrome if no known content container is found.
    Also promotes lazy `data-src` to `src` so the extracted HTML has working images.
    """
    soup = BeautifulSoup(html, "lxml")

    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        title = h1.get_text(strip=True)

    # Strip global chrome + widgets up front.
    for sel in STRIP_SELECTORS:
        for el in soup.select(sel):
            el.decompose()

    body = soup.body or soup
    body_len = len(body.get_text(strip=True))

    # Accept a positive content container only if it holds most of the page's
    # remaining text (>=55%); otherwise it's a sub-widget — use the whole body.
    container = body
    for sel in CONTENT_SELECTORS:
        found = soup.select_one(sel)
        if found:
            n = len(found.get_text(strip=True))
            if n > 60 and body_len and n >= 0.55 * body_len:
                container = found
                break

    # Promote lazy-loaded images so the saved HTML/Markdown references real files.
    for img in container.find_all("img"):
        for attr in ("data-src", "data-lazy-src", "data-original"):
            v = _clean_url(img.get(attr))
            if v and "/wp-content/uploads/" in v:
                img["src"] = urljoin(base_url, v)
                break

    return str(container), title


# ---------------------------------------------------------------------------
# Robust HTML -> Markdown fallback (pandoc drops content on this theme's
# malformed Bootstrap-carousel markup; this walker is resilient to bad nesting).
# ---------------------------------------------------------------------------

def visible_text_len(html):
    s = BeautifulSoup(html, "lxml")
    for t in s(["script", "style", "noscript"]):
        t.extract()
    return len(re.sub(r"\s+", " ", s.get_text(" ")).strip())


def _md_inline(el):
    parts = []
    for c in getattr(el, "children", []):
        if isinstance(c, NavigableString):
            parts.append(re.sub(r"\s+", " ", str(c)))
        elif c.name in ("strong", "b"):
            t = _md_inline(c).strip()
            parts.append(f"**{t}**" if t else "")
        elif c.name in ("em", "i"):
            t = _md_inline(c).strip()
            parts.append(f"*{t}*" if t else "")
        elif c.name == "a":
            t = _md_inline(c).strip()
            href = (c.get("href") or "").strip()
            parts.append(f"[{t}]({href})" if href and t else t)
        elif c.name == "br":
            parts.append("  \n")
        elif c.name == "img":
            src = (c.get("src") or c.get("data-src") or "").strip()
            parts.append("" if _is_junk_img(src) else f"![{c.get('alt', '')}]({src})")
        else:
            parts.append(_md_inline(c))
    return "".join(parts)


_HEADING_RE = re.compile(r"^h[1-6]$")


def _walk_blocks(el, out):
    for c in getattr(el, "children", []):
        if isinstance(c, Comment):
            continue
        if isinstance(c, NavigableString):
            txt = re.sub(r"\s+", " ", str(c)).strip()
            if txt and not _CODE_TEXT_RE.search(txt):
                out.append(txt)
            continue
        name = c.name or ""
        if name in ("script", "style", "noscript"):
            continue
        if _HEADING_RE.match(name):
            t = _md_inline(c).strip()
            if t:
                out.append(f"\n{'#' * int(name[1])} {t}\n")
        elif name == "p":
            t = _md_inline(c).strip()
            if t:
                out.append(f"\n{t}\n")
        elif name in ("ul", "ol"):
            for li in c.find_all("li", recursive=False):
                t = _md_inline(li).strip()
                if t:
                    out.append(f"- {t}")
            out.append("")
        elif name == "blockquote":
            t = _md_inline(c).strip()
            if t:
                out.append(f"\n> {t}\n")
        elif name == "img":
            src = (c.get("src") or c.get("data-src") or "").strip()
            if not _is_junk_img(src):
                out.append(f"\n![{c.get('alt', '')}]({src})\n")
        elif name == "hr":
            out.append("\n---\n")
        else:  # div, section, span, article, li-wrappers, etc. -> recurse
            _walk_blocks(c, out)


def html_to_markdown_fallback(html):
    """Order-preserving HTML->Markdown that tolerates broken nesting."""
    soup = BeautifulSoup(html, "lxml")
    out = []
    _walk_blocks(soup.body or soup, out)
    md = "\n".join(out)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()
