# Box House Hotel — new site: shared design system & build rules

Canonical reference implementation: **`site/Home.dc.html`** (already built & verified).
Every page MUST match its top bar, nav header, and footer byte-for-byte (only the
active nav link changes). When in doubt, copy those blocks from `Home.dc.html`.

## Design tokens (colors)
| Token | Hex | Use |
|---|---|---|
| Cream page bg | `#F7F3EA` | body background |
| Alt section bg | `#EFE8D8` | alternating panels |
| Ink | `#23211C` | body text |
| Muted | `#6B6455` | secondary text |
| Charcoal | `#141210` | dark sections / footer |
| Near-black | `#0D0C0A` | top utility bar |
| Cream text | `#E9E2D3` | text on dark |
| Warm grey | `#A79F8F` / `#7A7469` | muted text on dark |
| Gold | `#C8A87A` | primary accent / buttons |
| Bronze | `#A9814F` | secondary accent / checks / links |
| Hairline light | `#E3DAC8` | borders on cream |
| Hairline dark | `#3A352D` / `#2C2823` | borders on dark |

## Fonts
- Headings/display: **Libre Caslon Text** (serif)
- UI/body: **Archivo** (sans, weights 400/500/600)
- Loaded via the Google Fonts `<link>` in the shared `<head>` below.

## Shared `<head>` (use verbatim; only change the `<title>`)
```html
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PAGE • The Box House Hotel</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="">
<link href="https://fonts.googleapis.com/css2?family=Libre+Caslon+Text:ital,wght@0,400;0,700;1,400&family=Archivo:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  body { margin:0; background:#F7F3EA; font-family:'Archivo',sans-serif; color:#23211C; }
  a { color:inherit; text-decoration:none; }
  a:hover { opacity:0.75; }
  /* room-card "Check Availability" outline buttons fill on hover (was style-hover in the canvas) */
  .btn-avail { transition:background .15s ease, color .15s ease; }
  .btn-avail:hover { background:#C8A87A; color:#141210; opacity:1; }
</style>
```

## Nav header (lives inside each hero as an absolutely-positioned overlay)
Logo → `./Home.dc.html`; 7 links; Book Now → booking URL. The **active page's link**
gets: `style="color:#C8A87A; border-bottom:1px solid #C8A87A; padding-bottom:3px;"`.
Order: Accommodations · About · Gallery · Dining · Offers · Rooftop · Contact.

## Converting a Claude Design `.dc.html` → implemented page
1. Drop `<script src="../support.js"></script>`, `<x-dc>`, `<helmet>` wrappers, and the
   trailing `<script type="text/x-dc">…</script>`. Move the `<helmet>` contents into `<head>`.
2. Resolve template vars: `{{ phone }}` → `718.383.3800`; `{{ bookingUrl }}` →
   `https://secure.webrez.com/hotel/1091/`.
3. `style-hover="background:#C8A87A; color:#141210;"` on outline buttons → delete the
   attribute and add `class="btn-avail"` (CSS already in shared head).
4. Keep the outer `<div style="min-width:1180px;">` and ALL inline layout **exactly** as
   designed. This is the **desktop** build — do NOT add mobile/responsive CSS yet
   (separate phase). Pixel-fidelity to the design is the goal.
5. Remove `data-screen-label="…"` attributes (canvas-only annotations).

## Image localization (CRITICAL — the site must not depend on the old servers)
Rewrite every image URL to a local path and ensure the file exists on disk:
- `https://theboxhousehotel.com/wp-content/uploads/<P>` → src `../assets/images/<P>`,
  file at `assets/images/<P>`.
- `https://theboxhousehotel.com/wp-content/themes/theboxhouse/images/<F>` → src
  `../assets/images/theme/<F>`, file at `assets/images/theme/<F>`.
- If a referenced file is missing locally, download the original:
  `curl -s -m 40 -A "Mozilla/5.0" --create-dirs -o assets/images/<P> "<original-url>"`
  (verify HTTP 200 & non-zero size; images are served on both `theboxhousehotel.com`
  and, for a few, `henrynorman.wpengine.com`).

## Per-page verification (must pass before you report done)
- `grep` the output file: **0** occurrences of `{{`, `x-dc`, `helmet`, `support.js`,
  `data-screen-label`, or `theboxhousehotel.com/wp-content` (all images localized).
- Every `<img src>` resolves to an existing file on disk.
- Render a full-page screenshot and inspect it:
  `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu --hide-scrollbars --window-size=1280,5000 --screenshot=<scratchpad>/<page>.png "file://<ABS>/site/<Page>.dc.html"`
  Read the PNG and confirm: hero + nav render, all photos load (no broken/blank),
  fonts applied, sections match the design order. Fix anything off, re-render.

## Page filenames (keep the `.dc.html` names so nav links resolve)
`Home` `Accommodations` `About` `Gallery` `Dining` `Offers` `Rooftop` `Contact`
(+ future: `Events`, room detail pages, etc.)
