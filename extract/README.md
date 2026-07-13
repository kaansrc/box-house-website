# Box House Hotel — content extractor

Recovers all content and images from the live WordPress site
`theboxhousehotel.com` (WP admin is inaccessible) into a clean, reusable archive
for the new Replit design. **No general crawler** — structured-first via the WP
REST API, with rendered-HTML fetch for what REST hides.

## Why it's built this way

- The REST API is open, so Pages/Posts/Media come as clean JSON.
- BUT the theme is a **page builder that stores layout in post-meta**, so the REST
  `content.rendered` body is nearly empty for the important pages (home, rooms,
  dining, offers…). The real content + images live in the **rendered front-end HTML**,
  where images are **lazy-loaded via `data-src`**.
- Rooms / special offers / gallery items are **custom post types not exposed in REST**
  (404); their URLs come from the sitemap.

So: REST for metadata + media list, rendered HTML for body + images, union of both
for the complete image set, plus a `wget` mirror as a visual reference.

## Run it (in order)

```bash
cd extract
pip install -r requirements.txt          # requests, beautifulsoup4, lxml (pandoc + wget are system)

python3 01_fetch_rest.py                  # -> raw/pages.json, posts.json, media.json
python3 02_fetch_html.py                  # -> raw/html/**, raw/html_index.json  (56 URLs)
python3 03_download_media.py              # -> assets/images/**, assets/media_manifest.json
python3 04_build_content.py               # -> content/**/*.md, index.json
bash    05_mirror.sh                       # -> mirror/  (optional visual snapshot)
```

Every stage is idempotent (re-runs skip already-downloaded images).

## Outputs (the deliverable)

```
content/          Markdown + YAML frontmatter, one file per page/room/offer/etc.
  pages/  rooms/  offers/  portfolio/  blog/
  *.source.html   preserved raw content region alongside each .md
assets/images/    all images, original /YYYY/MM/ upload paths preserved
assets/media_manifest.json   every image: url, local path, alt, caption, size, source
index.json        master list of every content item + the images it uses
```

`raw/` (intermediate JSON/HTML) and `mirror/` (snapshot) are gitignored — regenerate
by re-running the scripts.

## Reusing this in the new design

- Read `index.json` for the page list; each entry points to its Markdown + images.
- Frontmatter carries `title`, `original_url`, `featured_image`, and `images[]`
  (all rewritten to local `/assets/images/...` paths).
- `assets/media_manifest.json` has `alt`/`caption` for accessible/SEO-friendly reuse.
