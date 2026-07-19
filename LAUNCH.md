# Launch runbook: DNS cutover to Replit

Step-by-step process for moving **theboxhousehotel.com** off the old WordPress host onto the Replit deployment, and retiring **theboxhousehotelevents.com** (Wix) with redirects into the new site.

The order matters: everything through Phase 3 is safe preparation that changes nothing visible. Only Phase 4 and 5 are the actual switch, and each has a clean rollback.

## Current state (recorded 2026-07-19) — keep for rollback

| | theboxhousehotel.com | theboxhousehotelevents.com |
|---|---|---|
| Registrar | GoDaddy | GoDaddy |
| Nameservers | ns63/ns64.domaincontrol.com (GoDaddy) | ns0/ns1.wixdns.net (Wix manages DNS) |
| Web | `@` A record → **104.196.188.81** (old WordPress host); `www` CNAME → `@` | Wix-managed records |
| Email | **Google Workspace** (MX aspmx.l.google.com etc., SPF `v=spf1 include:_spf.google.com ~all`) — MUST NOT be touched | MX → mailgun.org (likely Wix form/inbox mail; see Phase 0) |
| Other TXT | 2× google-site-verification | 1× google-site-verification |

Rollback at any point: hotel = set the `@` A record back to `104.196.188.81`; events = set nameservers back to `ns0.wixdns.net` / `ns1.wixdns.net`. The old WordPress site and the Wix site both keep running at their hosts until you cancel them (Phase 6), so rollback is instant and lossless.

## Phase 0 — decisions before touching anything

1. **Recipient mailboxes (confirmed 2026-07-19):** events forms → `hostyourevent@theboxhousehotel.com`; contact form with the "Accommodations & Reservations" topic → `reservations@theboxhousehotel.com`; all other contact topics → `info@theboxhousehotel.com`. These are the code defaults, so no secrets are needed unless an address changes. Confirm all three mailboxes exist in Google Workspace.
2. **Ask the team whether anyone receives email at `@theboxhousehotelevents.com`.** The domain has Mailgun MX records (typically Wix's form/inbox mail). If real mail arrives there, plan to move those senders to the hotel domain, or re-add the MX records in Phase 5 step 2.
3. Latest `main` is deployed state: includes the host-redirect logic in `server.js` (www and the events domain 301 to theboxhousehotel.com; the events homepage lands on `/box-house-events/`, old Wix slugs like `/wedding` map to their new pages).

## Phase 1 — deploy on Replit (no DNS involved)

1. replit.com → **Create Repl → Import from GitHub** → `kaansrc/box-house-website` (connect the GitHub account first; the repo is private).
2. Nothing to configure in code: `.replit` is already set up (Autoscale deployment, `node server.js`, port 8080 → 80).
3. Click **Deploy → Autoscale**. In the deployment's **Secrets**, add:
   - `RESEND_API_KEY` — from resend.com (same account as vesper.events)
   - `INQUIRY_FROM` — leave unset for now; set in Phase 2 step 3
   - (recipient addresses need no secrets; the defaults are the confirmed mailboxes from Phase 0)
4. Smoke-test on the `*.replit.app` URL:
   - `/`, `/rooms/`, `/box-house-events/`, `/weddings/`, `/post/social-gathering-in-brooklyn/` all render
   - `/sitemap.xml` and `/robots.txt` serve
   - `/specialoffer/brooklyn-romance` 301s to `/special-offers/`
   - Submit the contact form and an event inquiry; both arrive (or appear in deployment logs if the key isn't set yet)

## Phase 2 — Resend domain verification (safe to do now; additive DNS only)

1. Resend dashboard → **Domains → Add domain** → `theboxhousehotel.com`.
2. Resend shows records to add: DKIM TXT record(s) plus MX + SPF TXT on a **send subdomain** (e.g. `send.theboxhousehotel.com`). Add exactly those in GoDaddy DNS for theboxhousehotel.com. They live on their own subdomain/selector names, so they cannot conflict with Google Workspace. **Do not edit the existing `@` MX or SPF records.**
3. When Resend shows "Verified", set the deployment secret `INQUIRY_FROM` to `The Box House Hotel <inquiries@theboxhousehotel.com>` and redeploy.
4. Submit a test inquiry; confirm it arrives from the branded sender and that reply-to is the guest's address.

## Phase 3 — link the domains in Replit (still no DNS changes)

1. Deployment → **Settings → Link a domain**. Add all four hostnames:
   `theboxhousehotel.com`, `www.theboxhousehotel.com`, `theboxhousehotelevents.com`, `www.theboxhousehotelevents.com`.
2. For each, Replit displays the DNS records it needs: an **A record + TXT** for apex domains, a **CNAME + TXT** for www. Write all of them down. They stay pending until Phases 4–5 add them.

## Phase 4 — cutover: theboxhousehotel.com (GoDaddy DNS edit)

Pick a low-traffic hour. Total edit time is ~5 minutes; propagation is usually minutes (GoDaddy default TTL is 1 hour).

1. Optional: an hour ahead, lower the `@` A record TTL to 600 seconds so a rollback would also take effect fast.
2. GoDaddy → theboxhousehotel.com → DNS. Make ONLY these changes:
   - `@` A record: `104.196.188.81` → the Replit A-record IP from Phase 3
   - Add Replit's TXT verification record(s)
   - `www`: set per Replit's instructions (CNAME to the Replit target), replacing the current `www` → `@` CNAME
3. Touch nothing else. MX, SPF, google-site-verification, and the Resend records from Phase 2 all stay.
4. In Replit, wait for the domains to show **Verified** and for the TLS certificate to issue (minutes up to ~1 hour).
5. Verify live:
   - `https://theboxhousehotel.com` shows the new site with a valid padlock
   - `https://www.theboxhousehotel.com/gallery/` 301s to the apex
   - `https://theboxhousehotel.com/specialoffer/brooklyn-romance` 301s to `/special-offers/`
   - Submit a form end-to-end
   - Send/receive a test email on the hotel's Google Workspace (confirms MX untouched)

## Phase 5 — cutover: theboxhousehotelevents.com (nameserver switch)

DNS for this domain currently lives inside Wix, so the move is a nameserver change back to GoDaddy.

1. GoDaddy → theboxhousehotelevents.com → **Nameservers → Change** → use GoDaddy's default nameservers. (From this moment the Wix site is no longer reachable on the domain; the Wix subscription itself stays active until Phase 6.)
2. In the now-editable GoDaddy DNS zone for the events domain, add the Replit records from Phase 3: `@` A + TXT, `www` CNAME + TXT. If Phase 0 step 2 found real mailboxes, also re-add the Mailgun MX records.
3. Wait for Replit to verify and issue certs. Nameserver changes can take up to 24–48 h to propagate everywhere, though it's usually far faster.
4. Verify the redirects:
   - `https://theboxhousehotelevents.com/` → `https://theboxhousehotel.com/box-house-events/`
   - `/wedding` → `/weddings/`, `/corporate` → `/corporate-events/`, `/faqs` → `/faq/`
   - `/post/social-gathering-in-brooklyn/` → same slug on theboxhousehotel.com

## Phase 6 — post-launch: SEO handover and decommission

1. **Google Search Console** (the site-verification TXT records already exist):
   - Verify both domain properties, submit `https://theboxhousehotel.com/sitemap.xml`
   - For the events property, run **Change of Address** → theboxhousehotel.com, so Google transfers its ranking signals
2. Update external links that point at the events domain: Instagram bios (@boxhouseevents), Google Business Profile, The Knot / WeddingWire / Here Comes The Guide listings.
3. After 1–2 weeks of stability:
   - Cancel the **Wix premium plan** (NOT the domain — both domain registrations must renew indefinitely; the 301s only work while you own them)
   - Cancel the old **WordPress hosting** (a full scrape already exists locally in `mirror/`, but take the host's own final backup too)
4. Ongoing monitoring: Replit deployment logs (form submissions log there), Resend dashboard (delivery status), and Search Console coverage reports over the first month.

## Quick reference: what redirects where

| Old URL | New URL |
|---|---|
| theboxhousehotelevents.com/ | theboxhousehotel.com/box-house-events/ |
| …events.com/wedding | /weddings/ |
| …events.com/corporate | /corporate-events/ |
| …events.com/socialevents | /private-events/ |
| …events.com/madrecatering | /madre-catering/ |
| …events.com/room11productions | /room-11-productions/ |
| …events.com/our-team | /our-team/ |
| …events.com/faqs | /faq/ |
| …events.com/post/&lt;slug&gt; | /post/&lt;slug&gt;/ (1:1) |
| www.theboxhousehotel.com/* | theboxhousehotel.com/* |
| /specialoffer/*, /suite, /penthouse, etc. | mapped by the LEGACY table in server.js |
