#!/usr/bin/env bash
# Build the read-only (static, view-only) workbench bundle for viva-human-atlas
# and (optionally) push it to the gh-pages branch under dashboard/.
#
# The bundle is a fully static client-side SPA (no server). It is built LOCALLY
# because this workspace depends on sibling repos by relative path
# (../pbg-biomodels, ../pbg-copasi, ../pbg-tellurium) that don't exist in CI.
#
# Usage:
#   scripts/publish_dashboard.sh                # build only -> reports/published/dashboard
#   scripts/publish_dashboard.sh --push         # build, then push to gh-pages
set -euo pipefail
WS_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$WS_ROOT/reports/published/dashboard"
BASE_PATH="/viva-human-atlas/dashboard"
INTERACTIVE_URL="https://github.com/vivarium-collective/viva-human-atlas"
PY="$WS_ROOT/.venv/bin"

rm -rf "$OUT"
PYTHONPATH="$WS_ROOT" "$PY/vivarium-workbench-publish" \
  --workspace "$WS_ROOT" --out "$OUT" \
  --base-path "$BASE_PATH" --interactive-url "$INTERACTIVE_URL"
find "$OUT" -name '*.map' -delete || true
touch "$OUT/.nojekyll"
echo "Built bundle at $OUT"
echo "Preview: (cd $OUT && python -m http.server 8000)  then open http://localhost:8000/viva-human-atlas/dashboard/  (or serve at root)"

if [[ "${1:-}" == "--push" ]]; then
  GHP="$(mktemp -d)"
  git -C "$WS_ROOT" worktree add -B gh-pages "$GHP" origin/gh-pages 2>/dev/null \
    || git -C "$WS_ROOT" worktree add -B gh-pages "$GHP" main
  # gh-pages holds ONLY the bundle: clear everything tracked, then add dashboard/.
  find "$GHP" -mindepth 1 -maxdepth 1 -not -name '.git' -exec rm -rf {} +
  mkdir -p "$GHP/dashboard"
  cp -R "$OUT"/. "$GHP/dashboard/"
  touch "$GHP/.nojekyll"
  git -C "$GHP" add -A
  git -C "$GHP" -c user.name="Eran Agmon" -c user.email="agmon.eran@gmail.com" \
    commit -q -m "Publish read-only workbench ($(git -C "$WS_ROOT" rev-parse --short HEAD))" || echo "no changes"
  git -C "$GHP" push -u origin gh-pages
  git -C "$WS_ROOT" worktree remove --force "$GHP"
  echo "Pushed to gh-pages -> https://vivarium-collective.github.io/viva-human-atlas/dashboard/"
fi
