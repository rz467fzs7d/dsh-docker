#!/usr/bin/env bash
set -Eeuo pipefail
python3 /opt/homelab/configure.py
exec /usr/local/bin/entrypoint.sh "$@"
