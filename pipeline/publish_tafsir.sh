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

mapfile -t artifacts < <(
  python3 - "$DIR/catalogue.json" "$DIR" <<'PY'
import json
import sys
from pathlib import Path

catalogue = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
base = Path(sys.argv[2])
for entry in catalogue.get("tafsir", []):
    print(base / entry["file"])
PY
)
if (( ${#artifacts[@]} == 0 )); then
  echo "no artifacts referenced in $DIR/catalogue.json" >&2
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
  --cache-control "no-cache, must-revalidate"

echo
echo "Verifying over the public domain..."
python3 "$(dirname "$0")/verify_tafsir.py"
