#!/usr/bin/env python3
"""Render explicit browser origins into the native Caddy configuration."""
import ipaddress
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent


def parse_origins(value):
    origins = []
    for raw in value.split(','):
        raw = raw.strip()
        if not raw or any(c.isspace() or ord(c) < 32 for c in raw):
            raise ValueError('Each allowed origin must be a nonempty HTTP(S) origin')
        url = urlsplit(raw)
        if (url.scheme not in {'http', 'https'} or url.username or url.password
                or url.path not in {'', '/'} or url.query or url.fragment or not url.hostname):
            raise ValueError('Origins cannot contain credentials, paths, queries or fragments')
        host = url.hostname.lower()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', host):
                raise ValueError('Invalid origin hostname')
        port = url.port
        if port is not None and not 1 <= port <= 65535:
            raise ValueError('Invalid origin port')
        authority = ('[' + host + ']') if ':' in host else host
        if port is not None:
            authority += ':' + str(port)
        origin = url.scheme + '://' + authority
        if origin not in origins:
            origins.append(origin)
    if len(origins) > 8 or len({urlsplit(o).scheme for o in origins}) != 1:
        raise ValueError('Use at most eight origins with one common transport')
    return origins


def render(origins, direct):
    authorities = [urlsplit(origin).netloc for origin in origins]
    redirects = '\n\t\t\t'.join(
        'trust ' + action + ' redirect uri domain exact ' + json.dumps(host) + ' path prefix /'
        for host in authorities for action in ['login', 'logout'])
    headers = '\n\t'.join('request_header -' + name for name in
                           ['Forwarded', 'X-Forwarded-For', 'X-Forwarded-Host', 'X-Forwarded-Proto']) if direct else ''
    source = (HERE / 'Caddyfile.template').read_text(encoding='utf-8')
    return (source.replace('@@HOMELAB_REDIRECTS@@', redirects)
            .replace('@@HOMELAB_ORIGINS@@', json.dumps(origins))
            .replace('@@HOMELAB_AUTHORITIES@@', json.dumps(authorities))
            .replace('@@HOMELAB_FORWARDED_HEADERS@@', headers))


def main():
    origins = parse_origins(os.environ.get('HOMELAB_PUBLIC_URLS') or os.environ['PUBLIC_URL'])
    primary = parse_origins(os.environ['PUBLIC_URL'])[0]
    if primary not in origins:
        raise ValueError('PUBLIC_URL must be one of HOMELAB_PUBLIC_URLS')
    Path('/etc/caddy/Caddyfile').write_text(
        render(origins, os.environ.get('CADDY_TRUSTED_PROXIES', 'none') == 'none'), encoding='utf-8')


if __name__ == '__main__':
    main()
