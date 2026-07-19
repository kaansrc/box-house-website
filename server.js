'use strict';
/*
 * The Box House Hotel — static site + one form endpoint.
 *
 * Serves the prebuilt pages in /site and images in /assets, and exposes a single
 * dynamic route, POST /api/inquiry, which validates a contact/event inquiry and
 * emails it via Resend (https://resend.com). Mirrors the vesper.events setup:
 * pages are static, only the form handler is server-side so the API key stays secret.
 *
 * Configure as Replit Secrets (or a local .env — see .env.example):
 *   RESEND_API_KEY          – from resend.com (without it, submissions are logged, not sent)
 *   INQUIRY_TO_EVENTS       – events leads (default hostyourevent@theboxhousehotel.com)
 *   INQUIRY_TO_GENERAL      – general contact leads (default info@theboxhousehotel.com)
 *   INQUIRY_TO_RESERVATIONS – contact-form reservation topics (default reservations@theboxhousehotel.com)
 *   INQUIRY_FROM       – a Resend-verified sender, e.g. "The Box House Hotel <inquiries@theboxhousehotel.com>"
 *
 * Node 18+ (uses global fetch). No dependencies.
 */
const http = require('http');
const fs = require('fs');
const path = require('path');

const ROOT = __dirname;
const PORT = process.env.PORT || 8080;
const HOST = process.env.HOST || '0.0.0.0';

const RESEND_API_KEY = process.env.RESEND_API_KEY || '';
const TO_EVENTS = process.env.INQUIRY_TO_EVENTS || 'hostyourevent@theboxhousehotel.com';
const TO_GENERAL = process.env.INQUIRY_TO_GENERAL || 'info@theboxhousehotel.com';
const TO_RESERVATIONS = process.env.INQUIRY_TO_RESERVATIONS || 'reservations@theboxhousehotel.com';
const FROM = process.env.INQUIRY_FROM || 'The Box House Hotel <onboarding@resend.dev>';

// ---- clean URLs (mirror the original WordPress permalinks; new pages follow the same style) ----
// Same page -> same URL as the live WP site. NOTE: on the old site /events/ was the
// Rooftop page ("Rooftop • The Box House"), so /events/ stays with Rooftop; the new
// events hub lives at /box-house-events/. Blog posts keep their exact Wix slugs under
// /post/ so theboxhousehotelevents.com/post/<slug> redirects map 1:1.
const ROUTES = {
  '/': 'Home',
  '/rooms/': 'Accommodations',
  '/about-the-box-house/': 'About',
  '/gallery/': 'Gallery',
  '/dining/': 'Dining',
  '/special-offers/': 'Offers',
  '/events/': 'Rooftop',
  '/contact/': 'Contact',
  '/faq/': 'FAQ',
  '/press/': 'Press',
  '/accessibility/': 'Accessibility',
  '/employment-opportunities/': 'Employment',
  '/privacy-policy/': 'Privacy',
  '/cookie-policy/': 'Cookies',
  '/sitemap/': 'Sitemap',
  '/box-house-events/': 'Events',
  '/weddings/': 'Weddings',
  '/corporate-events/': 'Corporate',
  '/private-events/': 'PrivateEvents',
  '/madre-catering/': 'Madre',
  '/room-11-productions/': 'Room11',
  '/our-team/': 'Team',
  '/blog/': 'Blog',
  '/post/wedding-planning-guide-box-house-brooklyn/': 'BlogWeddingPlanningGuide',
  '/post/inclusive-weddings-events-in-brooklyn/': 'BlogInclusiveWeddings',
  '/post/hosting-an-elegant-holiday-party-in-brooklyn/': 'BlogHolidayParty',
  '/post/how-to-host-a-memorable-social-event-in-a-unique-venue/': 'BlogMemorableSocialEvent',
  '/post/choose-box-house-events-nyc-wedding-brooklyn/': 'BlogChooseBoxHouse',
  '/post/social-gathering-in-brooklyn/': 'BlogSocialGathering',
};

// Once DNS is cut over, the deployment answers on several hostnames; everything
// 301s to the canonical apex. The retired events domain's homepage maps to the
// events hub; its other slugs are translated by LEGACY below in the same hop.
const CANONICAL_HOST = 'theboxhousehotel.com';
const ALT_HOSTS = new Set([
  'www.theboxhousehotel.com',
  'theboxhousehotelevents.com',
  'www.theboxhousehotelevents.com',
]);

// Root-level SEO/discovery files.
const ROOT_FILES = {
  '/sitemap.xml': ['sitemap.xml', 'application/xml; charset=utf-8'],
  '/robots.txt': ['robots.txt', 'text/plain; charset=utf-8'],
  '/llms.txt': ['llms.txt', 'text/plain; charset=utf-8'],
};

// 301s for URLs that existed on the old WordPress site or the events Wix site
// but have no 1:1 page here. Keyed WITHOUT the trailing slash.
const LEGACY = {
  // events site (theboxhousehotelevents.com) slugs
  '/wedding': '/weddings/',
  '/corporate': '/corporate-events/',
  '/socialevents': '/private-events/',
  '/madrecatering': '/madre-catering/',
  '/room11productions': '/room-11-productions/',
  '/our-services': '/box-house-events/',
  '/faqs': '/faq/',
  // old WP offer detail pages
  '/specialoffer': '/special-offers/',
  '/specialoffer/brooklyn-romance': '/special-offers/',
  '/specialoffer/loyalty-promotion': '/special-offers/',
  '/specialoffer/the-long-haul': '/special-offers/',
  '/specialoffer/weekday-offer': '/special-offers/',
  // old WP room-type and misc pages folded into current pages
  '/room': '/rooms/',
  '/standard-room': '/rooms/',
  '/suite': '/rooms/',
  '/apartment': '/rooms/',
  '/apartments': '/rooms/',
  '/penthouse': '/rooms/',
  '/penthouses': '/rooms/',
  '/box-house-hotel-group': '/about-the-box-house/',
  '/culture': '/about-the-box-house/',
  '/local-guide': '/about-the-box-house/',
  '/covid-19': '/faq/',
  '/gallery-demo-1': '/gallery/',
};

const MIME = {
  '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8',
  '.webp': 'image/webp', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
  '.gif': 'image/gif', '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.txt': 'text/plain; charset=utf-8',
  '.webmanifest': 'application/manifest+json', '.woff2': 'font/woff2', '.woff': 'font/woff',
};

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function send(res, status, type, body, headers) {
  res.writeHead(status, Object.assign({ 'Content-Type': type }, headers || {}));
  res.end(body);
}

// ---- static file serving (only /site and /assets are exposed) ----
function serveStatic(req, res) {
  let urlPath = decodeURIComponent((req.url.split('?')[0] || '/'));
  if (urlPath === '/favicon.ico') urlPath = '/assets/images/theme/favicon.png';
  if (urlPath === '/healthz') return send(res, 200, 'text/plain', 'ok');

  const host = (req.headers.host || '').toLowerCase().split(':')[0];
  if (ALT_HOSTS.has(host)) {
    const bare = urlPath.length > 1 && urlPath.endsWith('/') ? urlPath.slice(0, -1) : urlPath;
    let target = LEGACY[bare] || urlPath;
    if (host.includes('events') && urlPath === '/') target = '/box-house-events/';
    const qs = req.url.includes('?') ? req.url.slice(req.url.indexOf('?')) : '';
    return send(res, 301, 'text/plain', 'Moved', { Location: 'https://' + CANONICAL_HOST + target + qs });
  }

  if (ROOT_FILES[urlPath]) {
    const [file, type] = ROOT_FILES[urlPath];
    res.writeHead(200, { 'Content-Type': type, 'Cache-Control': 'no-cache' });
    return fs.createReadStream(path.join(ROOT, file)).pipe(res);
  }

  const noSlash = urlPath.length > 1 && urlPath.endsWith('/') ? urlPath.slice(0, -1) : urlPath;
  if (LEGACY[noSlash]) {
    return send(res, 301, 'text/plain', 'Moved', { Location: LEGACY[noSlash] });
  }

  // Clean URLs: serve the mapped page; 301 the slashless form to the canonical
  // trailing-slash URL, exactly like WordPress did.
  if (ROUTES[urlPath]) {
    const filePath = path.join(ROOT, 'site', ROUTES[urlPath] + '.dc.html');
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-cache' });
    return fs.createReadStream(filePath).pipe(res);
  }
  if (urlPath !== '/' && ROUTES[urlPath + '/']) {
    return send(res, 301, 'text/plain', 'Moved', { Location: urlPath + '/' });
  }

  const top = urlPath.split('/')[1];
  if (top !== 'site' && top !== 'assets') return send(res, 404, 'text/plain', 'Not found');

  const filePath = path.normalize(path.join(ROOT, urlPath));
  if (!filePath.startsWith(path.join(ROOT, 'site')) && !filePath.startsWith(path.join(ROOT, 'assets'))) {
    return send(res, 403, 'text/plain', 'Forbidden'); // path-traversal guard
  }
  fs.stat(filePath, (err, st) => {
    if (err || !st.isFile()) return send(res, 404, 'text/plain', 'Not found');
    const type = MIME[path.extname(filePath).toLowerCase()] || 'application/octet-stream';
    const cache = top === 'assets' ? 'public, max-age=31536000, immutable' : 'no-cache';
    res.writeHead(200, { 'Content-Type': type, 'Cache-Control': cache });
    fs.createReadStream(filePath).pipe(res);
  });
}

// ---- POST /api/inquiry ----
function handleInquiry(req, res) {
  let raw = '';
  let tooBig = false;
  req.on('data', (c) => {
    raw += c;
    if (raw.length > 65536) { tooBig = true; req.destroy(); }
  });
  req.on('end', () => {
    if (tooBig) return finish(res, req, false, 'Your message is too long.', 413);
    const wantsJson = (req.headers['accept'] || '').includes('application/json');
    let f;
    try { f = new URLSearchParams(raw); } catch (_) { f = new URLSearchParams(''); }
    const get = (k) => (f.get(k) || '').toString().trim();

    // Honeypot: bots fill the hidden field. Silently "succeed".
    if (get('_honey')) return finish(res, req, true);

    const formType = get('formType') === 'events' ? 'events' : 'contact';
    const name = (get('first_name') + ' ' + get('last_name')).trim();
    const email = get('email');
    const message = get('message');
    const topic = get('topic');
    const eventType = get('event_type');
    const eventDate = get('event_date');

    if (!email || !EMAIL_RE.test(email) || message.length < 10) {
      return finish(res, req, false, 'Please complete the required fields with a valid email and a short message.', 400);
    }
    if (name.length > 200 || message.length > 5000) {
      return finish(res, req, false, 'Please shorten your message.', 400);
    }
    // Phone optional; if present must be a 10-digit US number.
    let digits = get('phone').replace(/\D/g, '');
    if (digits.length === 11 && digits.startsWith('1')) digits = digits.slice(1);
    if (get('phone') && digits.length !== 10) {
      return finish(res, req, false, 'Please enter a 10-digit US phone number.', 400);
    }
    const phoneFmt = digits.length === 10 ? `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}` : '';

    // Contact-form routing: reservation topics go to the front desk, the rest to info@.
    const to = formType === 'events' ? TO_EVENTS
      : /reservation|accommodation/i.test(topic) ? TO_RESERVATIONS
      : TO_GENERAL;
    const kind = formType === 'events' ? (eventType || 'Event') : (topic || 'General');
    const subject = `New ${formType === 'events' ? 'event ' : ''}inquiry — ${name || email} · ${kind}`;
    const lines = [
      `Source: ${formType === 'events' ? 'Events form' : 'Contact form'}`,
      `Name: ${name || '(not given)'}`,
      `Email: ${email}`,
      phoneFmt && `Phone: ${phoneFmt}`,
      formType === 'contact' && topic && `Topic: ${topic}`,
      formType === 'events' && eventType && `Event type: ${eventType}`,
      formType === 'events' && eventDate && `Preferred date: ${eventDate}`,
      '', message,
    ].filter(Boolean).join('\n');

    deliver({ to, replyTo: email, subject, text: lines })
      .then(() => finish(res, req, true))
      .catch((err) => {
        console.error('[inquiry] send failed:', err && err.message ? err.message : err);
        finish(res, req, false, 'Something went wrong sending your inquiry. Please email or call us directly.', 502);
      });
  });
}

async function deliver({ to, replyTo, subject, text }) {
  if (!RESEND_API_KEY) {
    console.log(`[inquiry] (RESEND_API_KEY not set — logging only)\nTo: ${to}\n${subject}\n${text}\n`);
    return;
  }
  const r = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: { Authorization: `Bearer ${RESEND_API_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ from: FROM, to, reply_to: replyTo, subject, text }),
  });
  if (!r.ok) throw new Error(`Resend ${r.status}: ${await r.text()}`);
}

// JSON for fetch/AJAX; a small branded HTML page for the no-JS form POST.
function finish(res, req, ok, error, status) {
  const wantsJson = (req.headers['accept'] || '').includes('application/json');
  if (wantsJson) {
    return send(res, ok ? 200 : (status || 400), 'application/json; charset=utf-8', JSON.stringify(ok ? { ok: true } : { ok: false, error }));
  }
  const title = ok ? 'Thank you' : 'Something went wrong';
  const body = ok
    ? 'Your message is on its way — we typically reply within one business day.'
    : esc(error || 'Please try again.');
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title} • The Box House Hotel</title>`
    + `<style>body{margin:0;background:#141210;color:#E9E2D3;font-family:Georgia,'Times New Roman',serif;display:flex;min-height:100vh;align-items:center;justify-content:center;text-align:center;padding:24px}`
    + `.c{max-width:520px}h1{font-weight:400;font-size:34px;margin:0 0 14px}p{font-family:Arial,sans-serif;color:#A79F8F;font-size:16px;line-height:1.6;margin:0 0 26px}`
    + `a{display:inline-block;background:#C87E5A;color:#141210;text-decoration:none;font-family:Arial,sans-serif;font-weight:600;letter-spacing:.12em;text-transform:uppercase;font-size:13px;padding:15px 30px}</style>`
    + `</head><body><div class="c"><h1>${title}</h1><p>${body}</p><a href="/">Back to the site</a></div></body></html>`;
  send(res, ok ? 200 : (status || 400), 'text/html; charset=utf-8', html);
}

const server = http.createServer((req, res) => {
  if (req.method === 'POST' && (req.url === '/api/inquiry' || req.url.startsWith('/api/inquiry?'))) {
    return handleInquiry(req, res);
  }
  if (req.method !== 'GET' && req.method !== 'HEAD') return send(res, 405, 'text/plain', 'Method not allowed');
  serveStatic(req, res);
});

server.listen(PORT, HOST, () => {
  console.log(`The Box House Hotel site running on http://${HOST}:${PORT}`);
  console.log(`  events -> ${TO_EVENTS}`);
  console.log(`  general -> ${TO_GENERAL}`);
  console.log(`  reservations -> ${TO_RESERVATIONS}`);
  console.log(`  resend -> ${RESEND_API_KEY ? 'configured' : 'NOT configured (submissions logged only)'}`);
});
