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
- Set the native `AUTH_USERNAME` and `AUTH_PASSWORD` through a deployment-only
  `.env` using Compose `env_file`. No duplicate alias variables are needed.
  Keep the actual `.env` outside this public fork; no deployment credential belongs here.
- Default `AUTH_MODE=basic` uses Caddy's native browser username/password challenge.
  The adapter hashes the password through stdin and removes the plaintext from
  the child environment. Ordinary HTTP routes require Basic credentials;
  existing DSH or portal cookies alone cannot bypass that gate. `/healthz` is a
  public readiness response. Basic Authorization headers are removed upstream.
- The exact `GET /api/remote.mux` WebSocket upgrade uses DSH's native signed-cookie
  authentication, preventing repeated browser Basic prompts when the handshake
  omits cached HTTP credentials. Missing and forged cookies are rejected by DSH
  before upgrade; Host and Origin checks still run in Caddy. Ordinary HTTP requests
  to the same path still require Basic authentication. Portal mode is unchanged.
- Explicit `AUTH_MODE=none` disables the outer login prompt for all permitted
  authorities. The adapter uses the upstream native passthrough lifecycle,
  automatically bootstraps DSH signed cookies, and retains Host/Origin restrictions.
  This is not source-subnet authentication. The settings proxy preserves the
  browser Host so cookies from secondary origins remain valid.
- Set `PUBLIC_URL` and comma-separated `HOMELAB_PUBLIC_URLS` to explicit HTTP(S)
  origins. The primary origin must be included. Mixed HTTP/HTTPS origins are rejected.
- Set `DSH_TRUSTED_HOSTS` to the permitted browser authorities.
- Direct connections use `CADDY_TRUSTED_PROXIES=none`; spoofed forwarding headers
  are removed. Reviewed HTTPS reverse proxies can supply explicit trusted CIDRs.
- HTTP requires the upstream `AUTH_COOKIE_INSECURE=true` setting. This adapter
  retains **HttpOnly** on every response cookie. HTTPS still keeps **Secure**.
- Basic credential caching is browser-controlled, without a portal logout button
  or a 30-day JWT session. For the previous form portal, set
  `AUTH_MODE=caddy-security`; its 30-day token and `/data/auth` state remain supported.
  The adapter reuses the unmodified upstream bootstrap lifecycle internally;
  Basic mode does not enable its portal or accept its JWT as authentication.
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

The integration probe uses disposable local data and tests the browser challenge,
wrong-password rejection, both origins, API access, cookie-only bypass rejection,
invalid native cookie recovery, hostile Host/Origin rejection and restart behavior.
Run with `--auth-mode none` for login-free origins, or `--auth-mode caddy-security` to check the retained portal mode separately.
Deployment-specific configuration is maintained in the private Homelab repository,
not in this public fork.
