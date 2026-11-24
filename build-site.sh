#!/usr/bin/env bash
set -euo pipefail
[[ "$SITE_BUILDER_COMMIT" =~ ^[0-9a-f]{40}$ ]]
root="$PWD"
mkdir -p out
builder="$(mktemp -d "${RUNNER_TEMP:?}/leaderboard-site-builder.XXXXXX")"
git -C "$builder" init -q
git -C "$builder" fetch -q --depth 1 https://github.com/HeOCR/heocr.github.io.git "$SITE_BUILDER_COMMIT"
git -C "$builder" checkout -q --detach FETCH_HEAD
[[ "$(git -C "$builder" rev-parse HEAD)" == "$SITE_BUILDER_COMMIT" ]]
pin="$(sha256sum results.json | cut -d ' ' -f 1)"
cp results.json out/results.json
for mode in build check; do
  flags=()
  if [[ "$mode" == check ]]; then flags+=(--check); fi
  python "$builder/scripts/build_leaderboard.py" --results "$root/out/results.json" --sha256 "$pin" --out-dir "$root/out" "${flags[@]}"
done
