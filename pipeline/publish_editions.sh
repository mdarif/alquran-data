#!/usr/bin/env bash
# Publish the edition artifacts to Cloudflare R2.
#
#   python3 pipeline/build_editions.py --db assets/quran.db --out dist/editions
#   pipeline/publish_editions.sh
#
# Bucket: al-quran-editions (APAC) → https://editions.alquranreader.com
# Same arrangement as al-quran-audio → audio.alquranreader.com.
#
# THREE THINGS THAT MUST NOT CHANGE
#
# 1. `--remote` on every object command. Without it wrangler writes to a LOCAL
#    simulated bucket and still prints "Upload complete" — a silent no-op. This
#    bit us the first time; the bucket read back empty while every upload had
#    "succeeded".
#
# 2. NO `--content-encoding gzip`. The artifacts are gzip *files*, not
#    gzip-encoded responses. Marking them encoded makes HTTP clients
#    transparently decompress, so the bytes the app receives stop matching the
#    catalogue's `sha256` and every install fails its integrity check.
#
# 3. Artifacts are content-addressed (`<slug>-<sha12>.db.gz`), so their bytes
#    never change and they are cached immutably. Only catalogue.json gets a
#    short TTL — it is the thing that changes when an edition is republished.
#
# Upload order matters: artifacts FIRST, catalogue LAST. The catalogue is what
# points at the files, so publishing it first opens a window where a client
# reads it and 404s on a file that isn't there yet.
set -euo pipefail

BUCKET="${BUCKET:-al-quran-editions}"
DIR="${1:-dist/editions}"

if [[ ! -f "$DIR/catalogue.json" ]]; then
  echo "no catalogue.json in $DIR — run build_editions.py first" >&2
  exit 1
fi

mapfile -t artifacts < <(
  python3 - "$DIR/catalogue.json" "$DIR" <<'PY'
import json
import sys
from pathlib import Path

catalogue = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
base = Path(sys.argv[2])
for entry in catalogue.get("editions", []):
    print(base / entry["file"])
PY
)
if (( ${#artifacts[@]} == 0 )); then
  echo "no artifacts referenced in $DIR/catalogue.json" >&2
  exit 1
fi

for f in "${artifacts[@]}"; do
  echo "→ $(basename "$f")"
  npx --yes wrangler r2 object put "$BUCKET/$(basename "$f")" \
    --file "$f" --remote \
    --content-type "application/gzip" \
    --cache-control "public, max-age=31536000, immutable"
done

echo "→ catalogue.json (last)"
npx --yes wrangler r2 object put "$BUCKET/catalogue.json" \
  --file "$DIR/catalogue.json" --remote \
  --content-type "application/json; charset=utf-8" \
  --cache-control "no-cache, must-revalidate"

echo
echo "Verifying over the public domain…"
python3 "$(dirname "$0")/verify_editions.py"
