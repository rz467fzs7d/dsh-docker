# DSH Docker for Homelab

This fork installs the official npm runtime and adds a native configuration adapter.
The upstream source builder remains an optional tool; the normal build changes no DSH source.

## Build on the Docker host

```sh
DOCKER_BUILDKIT=1 python3 deepseek-harness-builder/homelab/build.py \
  --base-image homelab/dsh:latest --tag homelab/dsh:upgrade \
  --receipt /tmp/dsh-build-receipt.json
python3 deepseek-harness-builder/homelab/smoke.py --image homelab/dsh:upgrade --auth-mode none
```

The normal build installs the official **published npm package and production
dependencies**, without compiling the DSH monorepo. Every invocation resolves the
highest published semantic version, including prereleases such as `alpha`; npm's
`latest` tag is not assumed to be the highest version. The version is resolved
once per build and its integrity is verified against npm's lockfile after install.
The receipt records the package version, integrity, engines, adapter revision and
base/final image config IDs. There is no committed DSH version pin.

Build on the deployment host to keep the resulting image there. Python 3 and Docker
with BuildKit/Buildx are required. Short-lived bridge containers supply Git, Node
and npm from the existing workstation image, mounting only source and temporary
context. No Docker socket is mounted. The existing Python/Go/Caddy toolchain stays
in the base image; npm's download cache is kept in BuildKit for subsequent updates.
Native dependencies may use their own install scripts or build a missing native
addon; this does not compile DSH's TypeScript/Web application sources.

`build_source.py` retains the upstream full-source build as an **explicit optional
path** for an unpublished version or source-development verification. It is not
called automatically when a package lookup or install fails. Ordinary Homelab
configuration, plugins, models and login adaptation do not require source builds.

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
