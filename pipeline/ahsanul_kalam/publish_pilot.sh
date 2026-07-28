#!/usr/bin/env bash
# Build -> check -> publish the Ahsanul Kalam pilot, as one gated command.
#
# Owner requirement 2026-07-28: the system checks everything, no manual pass. The
# gate is the point of this script. Before it existed the flow was build, then
# verify, then a human decided by eye which surahs looked safe to copy — which is
# the manual step wearing a different hat, and it shipped two corrupted surahs
# (Hud carrying Yusuf's verses, ad-Dukhan carrying al-Jathiyah's).
#
# Now nothing reaches the web repo unless verify_pilot.py exits 0. Quarantined
# surahs are simply absent, exactly as the site's all-or-nothing-per-surah pilot
# rule already expects.
#
#   pipeline/ahsanul_kalam/publish_pilot.sh            # full rebuild + publish
#   pipeline/ahsanul_kalam/publish_pilot.sh --no-build # re-check + publish only
set -euo pipefail

cd "$(dirname "$0")/../.."

SRC=${SRC:-sources/ahsanul-kalam}
DIST=${DIST:-dist/pilot/ahsanul-kalam}
WEB=${WEB:-../al-quran-web/data/ahsanul-kalam}
SURAHS=${SURAHS:-1-114}
JOBS=${JOBS:-10}

if [[ "${1:-}" != "--no-build" ]]; then
  echo "==> build (surahs $SURAHS)"
  python3 pipeline/ahsanul_kalam/build_pilot.py \
    --src "$SRC" --out "$DIST" --surahs "$SURAHS" --jobs "$JOBS"
fi

# --apply performs the repairs the evidence decides (nukta restoration, मैं/में by
# bigram) and writes per-verse flags. It exits non-zero while anything is
# unresolved, so `set -e` stops the publish here rather than shipping it.
echo "==> verify + repair"
python3 pipeline/ahsanul_kalam/verify_pilot.py --pilot "$DIST" --apply --quarantine

echo "==> publish to $WEB"
if [[ ! -d "$WEB" ]]; then
  echo "no web data dir at $WEB — is al-quran-web checked out?" >&2
  exit 1
fi
# Clear first: a surah withdrawn by the gate must DISAPPEAR from the site, not
# linger from a previous run. This is how the corrupt Hud survived one cycle.
rm -f "$WEB"/surah-*.json
cp "$DIST"/surah-*.json "$WEB"/

echo "==> $(ls "$WEB"/surah-*.json | wc -l | tr -d ' ') surah(s) published"
echo "    now run 'npm run export' in al-quran-web"
