#!/usr/bin/env bash
# Publish a translation-audio source directory (plain SSSAAA.mp3 files, no
# catalogue/manifest — see docs/translation-audio-r2-publish-plan.md for the
# 7-file Al-Fatihah pilot this generalizes) to Cloudflare R2.
#
#   pipeline/publish_translation_audio.sh <source-dir> <r2-prefix> [bucket]
#
# Example (full Sahih International set, once fully fetched):
#   pipeline/publish_translation_audio.sh \
#     sources/audio/sahih-international \
#     translation-audio/en-sahih-international
#
# Bucket defaults to al-quran-audio (same bucket recitation/ already lives
# in; translation-audio/ is a sibling prefix, not nested under recitation/).
#
# RESUMABLE: successfully-uploaded keys are appended to a manifest file next
# to the source dir (<source-dir>.uploaded) and skipped on a re-run — safe to
# Ctrl-C and restart, or to run this after every incremental fetch batch
# instead of waiting for all 6236 files.
#
# THINGS THAT MUST NOT CHANGE (see publish_editions.sh for the editions-bucket
# version of this warning — same trap, different bucket):
#
# 1. `--remote` on every object command. Without it wrangler writes to a
#    LOCAL simulated bucket and still prints "Upload complete" — a silent
#    no-op that looks identical to a real publish.
# 2. Content-Type stays `audio/mpeg`, no Content-Encoding. These are real
#    MP3s served as-is, not gzip artifacts — there is no decode-mismatch trap
#    here, but don't add one by "helpfully" gzip-wrapping them.
set -euo pipefail

SRC="${1:?usage: $0 <source-dir> <r2-prefix> [bucket]}"
PREFIX="${2:?usage: $0 <source-dir> <r2-prefix> [bucket]}"
BUCKET="${3:-al-quran-audio}"
MANIFEST="${SRC%/}.uploaded"

if [[ ! -d "$SRC" ]]; then
  echo "no such source directory: $SRC" >&2
  exit 1
fi
touch "$MANIFEST"

total=0
uploaded=0
skipped=0
failed=0

# Sorted so progress output is predictable and a partial run resumes in a
# sensible order (surah 1 before surah 114).
while IFS= read -r f; do
  key="$(basename "$f")"
  total=$((total + 1))
  if grep -qxF "$key" "$MANIFEST"; then
    skipped=$((skipped + 1))
    continue
  fi
  if npx --yes wrangler r2 object put "$BUCKET/$PREFIX/$key" \
      --file "$f" --remote \
      --content-type "audio/mpeg" \
      --cache-control "public, max-age=31536000, immutable" >/dev/null 2>&1; then
    echo "$key" >> "$MANIFEST"
    uploaded=$((uploaded + 1))
  else
    echo "FAILED: $key" >&2
    failed=$((failed + 1))
  fi
  if (( total % 100 == 0 )); then
    echo "[$PREFIX] $total processed — $uploaded uploaded, $skipped already done, $failed failed"
  fi
done < <(find "$SRC" -maxdepth 1 -name '*.mp3' | sort)

echo
echo "[$PREFIX] done: $total total, $uploaded uploaded this run, $skipped already done, $failed failed"
if (( failed > 0 )); then
  echo "Re-run this same command — it will retry only what's missing from $MANIFEST." >&2
  exit 1
fi
