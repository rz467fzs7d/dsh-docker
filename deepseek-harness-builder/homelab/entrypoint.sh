#!/usr/bin/env bash
set -Eeuo pipefail
if [[ "${AUTH_MODE:-basic}" == basic ]]; then
    AUTH_PASSWORD_HASH="$(python3 /opt/homelab/configure.py --auth-mode basic)"
    export AUTH_PASSWORD_HASH
    unset AUTH_PASSWORD AUTH_PASSWORD_FILE
    # Reuse the upstream launch-token/bootstrap lifecycle, with our rendered
    # native basic_auth configuration in place of its authentication portal.
    export AUTH_MODE=caddy-security
else
    python3 /opt/homelab/configure.py --auth-mode "${AUTH_MODE}"
fi
exec /usr/local/bin/entrypoint.sh "$@"
