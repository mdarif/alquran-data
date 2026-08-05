#!/usr/bin/env bash
# Publish Tafsir artifacts to the editions R2 bucket under /tafsir/.
#
#   python3 pipeline/build_tafsir.py --config config/tafsir.yaml --out dist/tafsir
#   pipeline/publish_tafsir.sh
#
# Bucket: al-quran-editions (APAC) -> https://editions.alquranreader.com/tafsir/
#
# Same rules as translation editions:
# - use --remote on every wrangler object command
# - do not set Content-Encoding: gzip
# - upload immutable artifacts first, catalogue.json last
set -euo pipefail

BUCKET="${BUCKET:-al-quran-editions}"
DIR="${1:-dist/tafsir}"
PREFIX="${PREFIX:-tafsir}"

if [[ ! -f "$DIR/catalogue.json" ]]; then
  echo "no catalogue.json in $DIR — run build_tafsir.py first" >&2
  exit 1
fi

shopt -s nullglob
artifacts=("$DIR"/*.db.gz)
if (( ${#artifacts[@]} == 0 )); then
  echo "no .db.gz artifacts in $DIR" >&2
  exit 1
fi

for f in "${artifacts[@]}"; do
  echo "-> $PREFIX/$(basename "$f")"
  npx --yes wrangler r2 object put "$BUCKET/$PREFIX/$(basename "$f")" \
    --file "$f" --remote \
    --content-type "application/gzip" \
    --cache-control "public, max-age=31536000, immutable"
done

echo "-> $PREFIX/catalogue.json (last)"
npx --yes wrangler r2 object put "$BUCKET/$PREFIX/catalogue.json" \
  --file "$DIR/catalogue.json" --remote \
  --content-type "application/json; charset=utf-8" \
  --cache-control "public, max-age=300, must-revalidate"

echo
echo "Verifying over the public domain..."
python3 "$(dirname "$0")/verify_tafsir.py"
