#!/usr/bin/env bash
# Re-sync logo SVGs from the desktop app's public/ folder.
#
# The brand assets (mark + wordmark, light + dark variants) live in
# frontend/public/ as the source of truth — that's where the React app
# reads them via /tokenmind-*.svg URLs. The landing site needs its own
# copies because Astro can't reach across to a sibling project's public/.
#
# Run this whenever the upstream SVGs change:
#   bash landing/scripts/sync-brand-assets.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="${ROOT}/frontend/public"
DST="${ROOT}/landing/public"

ASSETS=(
  tokenmind-mark.svg
  tokenmind-mark-black.svg
  tokenmind-sidebar-wordmark.svg
  tokenmind-sidebar-wordmark-black.svg
  tokenmind-wordmark.svg
  tokenmind-wordmark-black.svg
)

for asset in "${ASSETS[@]}"; do
  cp "${SRC}/${asset}" "${DST}/${asset}"
done

echo "Synced ${#ASSETS[@]} brand SVGs to landing/public/"
