#!/usr/bin/env bash
set -euo pipefail

log_file="${TMPDIR:-/tmp}/robinhood-mcp-smoke.log"
rm -f "$log_file"

python -m robinhood_mcp.server >"$log_file" 2>&1 &
pid=$!

cleanup() {
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    wait "$pid" || true
  fi
}
trap cleanup EXIT

sleep 2
if ! kill -0 "$pid" 2>/dev/null; then
  echo "robinhood-mcp exited early during startup" >&2
  if [ -s "$log_file" ]; then
    cat "$log_file" >&2
  fi
  exit 1
fi
