# Box House Hotel — Content Extractor (WP → archive)

**Date:** 2026-07-11
**Status:** Approved design
**Repo:** `box-house-website` (staging archive; new Replit design lives in a separate repo)

## Problem

We're migrating `theboxhousehotel.com` off WordPress. WP admin is inaccessible, so
content and images must be recovered from the live site and archived here for reuse
in the new design.

## Key facts (from live recon, 2026-07-11)

- Site is **WordPress with the REST API fully open** (no auth for published content).
- **24 Pages**, **1 Post**, **462 Media items** — all available as structured JSON via
  `/wp-json/wp/v2/{pages,posts,media}`.
- **Custom post types** `room`, `specialoffer`, `portfolio_item`, `portfolio_grid` are
  **NOT** exposed via REST (404). Their URLs are enumerable from the sitemap
  (`wp-sitemap-posts-{room,specialoffer,portfolio_item,portfolio_grid}-1.xml`) and must
  be fetched as HTML.
- `robots.txt`: only `/wp-admin/` disallowed; `Crawl-delay: 10`; sitemap at
  `/wp-sitemap.xml`.

## Decision

**No general crawler.** Structured-first extraction via the REST API; targeted HTML
fetch only for the custom-post-type gap. Output = Markdown + frontmatter + local images
+ a visual `wget` mirror.

## Toolchain (all already installed)

`python3`, `requests`, `beautifulsoup4`, `lxml`, **`pandoc`** (HTML→Markdown), **`wget`**
(mirror). No mandatory pip installs; `requirements.txt` pins the Python deps for
reproducibility.

## Components (`extract/`, each single-purpose)

1. **`01_fetch_rest.py`** — paginate Pages/Posts/Media from REST → `raw/pages.json`,
   `raw/posts.json`, `raw/media.json`.
2. **`02_fetch_cpt.py`** — read room/specialoffer/portfolio sub-sitemaps, fetch each
   page's HTML → `raw/html/<type>/<slug>.html` + `raw/cpt_index.json`.
3. **`03_download_media.py`** — download all media (+ image URLs discovered in page/CPT
   HTML) → `assets/images/<uploads-path>`; write `assets/media_manifest.json`
   (orig URL → local path, alt, caption, w/h). Failures → `assets/errors.log`.
4. **`04_build_content.py`** — per page/post/CPT: rewrite `<img src>`/`srcset` remote→local,
   convert body HTML→Markdown via pandoc, write `content/<section>/<slug>.md` with YAML
   frontmatter (title, slug, original_url, date, featured_image, images[], source_type)
   and preserve raw HTML alongside. Build master `index.json`.
5. **`05_mirror.sh`** — one polite `wget --mirror --page-requisites --convert-links
   --adjust-extension --wait=1 --random-wait` pass → browsable `mirror/`.

## Output layout

```
box-house-website/
  extract/           # scripts + README + requirements.txt
  content/           # DELIVERABLE: pages/ rooms/ offers/ portfolio/  (.md + frontmatter)
  assets/images/     # DELIVERABLE: all images, uploads paths preserved
  assets/media_manifest.json
  index.json         # master index of every page + its images
  raw/               # intermediate JSON/HTML (gitignored)
  mirror/            # visual snapshot (gitignored, large)
```

## Data flow

`sitemaps + REST API → raw/ → (03 download images) + (04 build markdown) → content/ +
assets/ + index.json`. `05_mirror` runs independently into `mirror/`.

## Error handling & verification

- Retry-with-backoff on 429/5xx; skip + log 404s; real User-Agent; modest inter-request wait.
- Idempotent re-runs (skip already-downloaded images).
- Final checks: assert `pages==24`, `media==462`, downloaded == manifest length (minus
  logged failures); grep `content/` to confirm **no remote `theboxhousehotel.com` image
  URLs leaked through** (every image local before reuse).

## Scope notes

- Room *pages* (Penthouse/Suites/Standard) come via the page API; room *CPT* entries via
  step 2 HTML fetch — both included.
- Blog is 1 post → captured but treated as negligible.
- `raw/` and `mirror/` are derived/large → `.gitignore`d; `content/` + `assets/` +
  `extract/` are the durable archive.

## Out of scope

- Rebuilding the new site (separate repo).
- WP theme HTML/CSS/JS reuse (redesign, not port).
- Any authenticated WP-admin export.
