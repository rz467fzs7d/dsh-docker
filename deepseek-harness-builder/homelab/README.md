# DSH Docker for Homelab

This fork keeps the upstream release builder and adds a native configuration adapter.
DSH itself is built by the upstream Dockerfile; this layer changes no DSH source.

## Build

```sh
python3 deepseek-harness-builder/homelab/build.py \
  --platform linux/amd64 --tag homelab/dsh:latest
```

Every invocation resolves the highest non-draft DSH source release, verifies the
tag, source commit and archive checksum, and runs Docker with `--pull`. It never
silently falls back to the committed DSH baseline. The actual version, source
checksum, fork revision and final image ID are saved in `dsh-build-receipt.json`.
The workstation includes Python and Go for portable Homelab skills.
The upstream resolver accepts `GITHUB_TOKEN` from the build process environment
when GitHub's anonymous API limit is exhausted. Supply an existing credential
through your credential manager; do not embed it in a Docker build argument,
command-line value or source file. The credential is not included in the image.

## Deployment contract

- Publish the container's Caddy port 8080 as host port **3080** using bridge networking.
- Mount `/data`, `/data/dsh`, `/workspace` and `/home/node` persistently. Nested
  `/data/dsh` mounts let an existing DSH_HOME remain in place during migration.
- Use the upstream `AUTH_PASSWORD_FILE`; no password or credential belongs in this public fork.
- Set `PUBLIC_URL` and comma-separated `HOMELAB_PUBLIC_URLS` to explicit HTTP(S)
  origins. The primary origin must be included. Mixed HTTP/HTTPS origins are rejected.
- Set `DSH_TRUSTED_HOSTS` to the permitted browser authorities.
- Direct connections use `CADDY_TRUSTED_PROXIES=none`; spoofed forwarding headers
  are removed. Reviewed HTTPS reverse proxies can supply explicit trusted CIDRs.
- HTTP requires the upstream `AUTH_COOKIE_INSECURE=true` setting. This adapter
  retains **HttpOnly** on every response cookie. HTTPS still keeps **Secure**.
- Session lifetime defaults to 30 days. Auth users and the JWT signing key persist in `/data/auth`.
- After password authorization, an invalid legacy native cookie on the root page
  triggers DSH's launch-token exchange again. Unauthenticated requests still
  require the password portal; API 401 responses retain their original status and headers.
- The inherited image healthcheck must be slowed with only `healthcheck.interval: 10m`
  on NAS. Do not add a Compose `healthcheck.test`, host networking or a Docker socket.

## Verify

```sh
python3 -m unittest discover -s deepseek-harness-builder/homelab -p 'test_*.py'
python3 deepseek-harness-builder/homelab/smoke.py --image homelab/dsh:latest
```

The integration probe uses disposable local data and tests real password login,
both origins, invalid legacy cookie recovery, cookie flags, hostile Host/Origin rejection and login persistence
after restart. Deployment-specific configuration is maintained in the private
Homelab repository, not in this public fork.
