#!/usr/bin/env bash
# Downloads the RARS jar (RISC-V simulator) used to run and test QuAsm, and
# verifies its SHA-256 before leaving it in place.
#
# Provenance of the digest below, stated plainly because it matters:
# the GitHub release metadata for TheThirdOne/rars v1.6 publishes the asset's
# size (1860244 bytes) but no digest -- the API's `digest` field is null for
# assets uploaded before GitHub began recording one. This value was therefore
# computed from our own downloads (two independent fetches, 2026-09-07, both
# 780f730e... and both matching the size GitHub reports).
#
# So this check is trust-on-first-use. It detects later accidental change --
# a truncated download, a corrupted cache, a silently re-uploaded asset -- and
# pins every machine to the same bytes we tested against. It is NOT a
# supply-chain guarantee: it cannot establish that the bytes we first fetched
# were the bytes upstream intended to publish.
set -euo pipefail
cd "$(dirname "$0")"

URL=https://github.com/TheThirdOne/rars/releases/download/v1.6/rars1_6.jar
SHA256=780f730eb457b1ba609e968accc2c8b77d8f92c3d9dbf30cc7fdb3cfb14e8c24
JAR=rars1_6.jar

curl -fL -o "$JAR" "$URL"

if command -v sha256sum >/dev/null 2>&1; then
  actual=$(sha256sum "$JAR" | cut -d' ' -f1)
elif command -v shasum >/dev/null 2>&1; then
  actual=$(shasum -a 256 "$JAR" | cut -d' ' -f1)
else
  actual=$(python3 -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$JAR")
fi

if [ "$actual" != "$SHA256" ]; then
  echo "ERROR: $JAR failed its SHA-256 check." >&2
  echo "  expected $SHA256" >&2
  echo "  got      $actual" >&2
  rm -f "$JAR"
  exit 1
fi

echo "$JAR verified (sha256 $SHA256)"
