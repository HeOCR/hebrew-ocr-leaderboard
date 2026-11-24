#!/usr/bin/env bash
set -euo pipefail
test -n "$GH_TOKEN"
gh auth setup-git
git clone --quiet --depth 1 https://github.com/HeOCR/heocr.github.io.git "$RUNNER_TEMP/leaderboard-site"
pin="$(sha256sum out/results.json | cut -d ' ' -f 1)"
site="$RUNNER_TEMP/leaderboard-site"
# Build from current main as well so a stale builder cannot overwrite newer site markup.
python "$site/scripts/build_leaderboard.py" --results "$PWD/out/results.json" --sha256 "$pin" --out-dir "$PWD/out" --check
cp out/leaderboard.html "$site/leaderboard.html"
cp out/en/leaderboard.html "$site/en/leaderboard.html"
mkdir -p "$site/leaderboard"
cp out/results.json "$site/leaderboard/results.json"
git -C "$site" add -- leaderboard.html en/leaderboard.html leaderboard/results.json
if git -C "$site" diff --cached --quiet; then exit 0; fi
site_revision="$(git -C "$site" rev-parse --short=12 HEAD)"
branch="automation/leaderboard/$pin-$site_revision"
if [[ -z "$(git -C "$site" ls-remote --heads origin "refs/heads/$branch")" ]]; then
  git -C "$site" switch -c "$branch"
  git -C "$site" -c user.name='heocr-leaderboard' -c user.email='heocr-leaderboard@users.noreply.github.com' commit -m 'chore: refresh leaderboard pages'
  git -C "$site" push origin "$branch"
fi
existing="$(gh pr list -R HeOCR/heocr.github.io --state all --head "$branch" --json number --jq 'length')"
if [[ "$existing" != 0 ]]; then exit 0; fi
printf 'Generated both leaderboard pages from results SHA-256 `%s`.\n\nThe pinned site builder reproduced both files with `--check`.\n' "$pin" > "$RUNNER_TEMP/leaderboard-pr.md"
gh pr create -R HeOCR/heocr.github.io --draft --base main --head "$branch" --title 'chore: refresh leaderboard pages' --body-file "$RUNNER_TEMP/leaderboard-pr.md"
