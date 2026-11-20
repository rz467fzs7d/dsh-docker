# The build entrypoint creates this base from a freshly resolved DSH release.
ARG BASE_IMAGE=homelab/dsh-upstream:build
FROM ${BASE_IMAGE}
ARG SOURCE_REVISION
ARG DSH_VERSION
LABEL org.opencontainers.image.source="https://github.com/rz467fzs7d/dsh-docker" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      org.opencontainers.image.version="${DSH_VERSION}"
COPY --chmod=0755 entrypoint.sh /opt/homelab/entrypoint.sh
COPY configure.py Caddyfile.template /opt/homelab/
COPY requirements.txt /opt/homelab/requirements.txt
COPY profile.sh /etc/profile.d/99-homelab-tools.sh
RUN python3 -m venv /opt/homelab-venv \
    && /opt/homelab-venv/bin/pip install --no-cache-dir --disable-pip-version-check -r /opt/homelab/requirements.txt
ENV AUTH_TOKEN_LIFETIME=2592000 CADDY_TRUSTED_PROXIES=none \
    PATH=/opt/homelab-venv/bin:${PATH}
ENTRYPOINT ["/usr/bin/tini", "--", "/opt/homelab/entrypoint.sh"]
