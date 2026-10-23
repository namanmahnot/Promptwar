#!/usr/bin/env bash
# Runs the agent (loopback only) and the gateway (public $PORT); exits if either dies so the host restarts us.
set -euo pipefail

# Per-boot shared secret between gateway and agent unless one is provided.
export INTERNAL_API_KEY="${INTERNAL_API_KEY:-$(python -c 'import secrets; print(secrets.token_hex(32))')}"

(cd /srv/agent && exec uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-server-header --log-level warning) &
(cd /srv/api && exec node src/index.js) &

wait -n
exit 1
