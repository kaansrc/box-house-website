#!/usr/bin/env bash
# Stage 5: polite full static mirror of the current site as a visual reference.
# Produces mirror/theboxhousehotel.com/ — a browsable, offline snapshot of the old
# design (HTML + CSS + JS + images). This is a *reference*, not the deliverable;
# the structured content lives in content/ and assets/.
set -euo pipefail

cd "$(dirname "$0")/.."   # repo root
mkdir -p mirror

echo "Mirroring https://theboxhousehotel.com/ into mirror/ (polite: 1s wait)…"

wget \
  --mirror \
  --page-requisites \
  --convert-links \
  --adjust-extension \
  --no-parent \
  --wait=1 --random-wait \
  --tries=3 --timeout=30 \
  --user-agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) BoxHouseArchiver/1.0" \
  --directory-prefix=mirror \
  --reject-regex '(/wp-admin/|/wp-login|/wp-json|/feed|/author/|/tag/|/category/|/comments/|\?|/attachment/|/embed/)' \
  https://theboxhousehotel.com/ \
  2>&1 | tail -40 || true   # wget exits non-zero on any 404; that's fine

echo
echo "Mirror complete. Open: mirror/theboxhousehotel.com/index.html"
du -sh mirror 2>/dev/null || true
