#!/usr/bin/env bash
# Serve the interactive vivarium-workbench for this workspace with a UTF-8
# locale forced. Companion to scripts/publish_dashboard.sh.
#
#   bash scripts/serve_dashboard.sh                 # 127.0.0.1:8141
#   bash scripts/serve_dashboard.sh 8200            # custom port
#   bash scripts/serve_dashboard.sh 8200 0.0.0.0    # custom port + host
#
# Why PYTHONUTF8=1: importing viva_human_atlas (via pbg_simbio/viva_superpowers)
# can leave the process's default I/O encoding at ASCII. The workbench's
# study-run path then writes a generated subprocess script containing non-ASCII
# bytes (em-dash 0xe2) with the default codec and dies on UnicodeEncodeError, so
# runs fail. Forcing UTF-8 makes `serve` deterministic regardless of the
# caller's locale — an interactive terminal usually already has LANG set, but a
# detached / tmux / cron / nohup launch often does not. Same fix the publisher
# already applies.
set -euo pipefail
export PYTHONUTF8=1
WS_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${1:-8141}"
HOST="${2:-127.0.0.1}"

# Prefer this workspace's venv binary; fall back to PATH (e.g. an activated venv).
BIN="$WS_ROOT/.venv/bin/vivarium-workbench"
[ -x "$BIN" ] || BIN="vivarium-workbench"

echo "serving $WS_ROOT at http://$HOST:$PORT (PYTHONUTF8=1)"
exec "$BIN" serve --workspace "$WS_ROOT" --port "$PORT" --host "$HOST"
