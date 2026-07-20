#!/usr/bin/env bash
# Compass — one-command backup of a family's Neon Postgres database to a file
# you own, on your own machine.
#
# Usage:
#   ./scripts/backup.sh "<neon-connection-string>" [family-label]
#
# The connection string is that family's DATABASE_URL — copy it from the Render
# service (Environment tab) or the Neon dashboard (Connection Details). Run this
# once per family. Output lands in backups/ (gitignored — never commit real data).
#
# Restore into an empty database with:
#   psql "<connection-string>" < backups/<the-file>.sql
#
# Requires pg_dump (Postgres client tools). On a Mac:  brew install libpq
# then add it to your PATH:  brew link --force libpq
set -euo pipefail

CONN="${1:?Usage: ./scripts/backup.sh \"<neon-connection-string>\" [family-label]}"
LABEL="${2:-family}"
DIR="$(cd "$(dirname "$0")/.." && pwd)/backups"
mkdir -p "$DIR"
OUT="$DIR/compass-${LABEL}-$(date +%Y-%m-%d_%H%M).sql"

echo "Backing up ${LABEL} → ${OUT}"
pg_dump "$CONN" > "$OUT"
echo "✓ Done — $(du -h "$OUT" | cut -f1)"
echo "  Keep this file somewhere safe (it holds all that family's records)."
echo "  Restore with:  psql \"<connection-string>\" < \"$OUT\""
