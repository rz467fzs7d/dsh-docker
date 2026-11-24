#!/usr/bin/env python3
"""Render explicit browser origins into the native Caddy configuration."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
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


def password_hash(environment):
    """Resolve native credential inputs without exposing plaintext in process arguments."""
    values = [environment.get(key, '') for key in
              ['AUTH_PASSWORD', 'AUTH_PASSWORD_FILE', 'AUTH_PASSWORD_HASH']]
    if sum(bool(value) for value in values) != 1:
        raise ValueError('Configure exactly one native password input')
    password, filename, hashed = values
    if hashed:
        match = re.fullmatch(r'bcrypt:(\d{2}):(\$2[aby]\$(\d{2})\$[./A-Za-z0-9]{53})', hashed)
        if not match or not 12 <= int(match[1]) <= 31 or match[1] != match[3]:
            raise ValueError('Invalid native bcrypt password hash')
        return match[2]
    if filename:
        password = Path(filename).read_text().rstrip('\n')
    if not 12 <= len(password) <= 1024 or any(ord(c) < 32 or ord(c) == 127 for c in password):
        raise ValueError('Password must contain 12 to 1024 characters without controls')
    result = subprocess.run(['caddy', 'hash-password', '--algorithm', 'bcrypt', '--bcrypt-cost', '12'],
                            input=password + '\n', text=True, capture_output=True, check=True)
    hashed = result.stdout.strip()
    if not re.fullmatch(r'\$2[aby]\$12\$[./A-Za-z0-9]{53}', hashed):
        raise ValueError('Caddy did not return a bcrypt password hash')
    return hashed


def render(origins, direct, auth_mode='caddy-security', hashed=None):
    authorities = [urlsplit(origin).netloc for origin in origins]
    redirects = '\n\t\t\t'.join(
        'trust ' + action + ' redirect uri domain exact ' + json.dumps(host) + ' path prefix /'
        for host in authorities for action in ['login', 'logout'])
    headers = '\n\t'.join('request_header -' + name for name in
                           ['Forwarded', 'X-Forwarded-For', 'X-Forwarded-Host', 'X-Forwarded-Proto']) if direct else ''
    source = (HERE / 'Caddyfile.template').read_text(encoding='utf-8')
    if auth_mode == 'basic':
        if not hashed or not re.fullmatch(r'\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}', hashed):
            raise ValueError('Basic authentication requires a bcrypt hash')
        global_auth, routes = '', ''
        snippets = '(dsh_basic) {\n\tbasic_auth @dsh_basic_required bcrypt DSH {\n\t\t{$AUTH_USERNAME} ' + hashed + '\n\t}\n}'
        # Browser WebSocket handshakes may omit cached HTTP Basic credentials.
        # The native mux verifies DSH's signed cookie before upgrading; do not
        # challenge again here or accept a cookie by its presence alone.
        basic_matchers = '''@dsh_basic_required {
        not {
            method GET
            path /api/remote.mux
            header Upgrade websocket
        }
    }'''
        authorize = 'import dsh_basic'
    elif auth_mode == 'caddy-security':
        global_auth = (HERE / 'auth-portal.Caddyfile').read_text(encoding='utf-8')
        routes = (HERE / 'auth-routes.Caddyfile').read_text(encoding='utf-8')
        snippets, authorize = '', 'authorize with dsh_policy'
        basic_matchers = ''
    elif auth_mode == 'none':
        global_auth = routes = snippets = authorize = basic_matchers = ''
    else:
        raise ValueError('Unsupported Homelab authentication mode')
    source = (source.replace('@@HOMELAB_AUTH_GLOBAL@@', global_auth)
              .replace('@@HOMELAB_AUTH_ROUTES@@', routes)
              .replace('@@HOMELAB_AUTH_SNIPPETS@@', snippets)
              .replace('@@HOMELAB_BASIC_MATCHERS@@', basic_matchers)
              .replace('@@HOMELAB_AUTHORIZE@@', authorize))
    return (source.replace('@@HOMELAB_REDIRECTS@@', redirects)
            .replace('@@HOMELAB_ORIGINS@@', json.dumps(origins))
            .replace('@@HOMELAB_AUTHORITIES@@', json.dumps(authorities))
            .replace('@@HOMELAB_FORWARDED_HEADERS@@', headers))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--auth-mode', choices=['basic', 'caddy-security', 'none'], default='caddy-security')
    args = parser.parse_args()
    origins = parse_origins(os.environ.get('HOMELAB_PUBLIC_URLS') or os.environ['PUBLIC_URL'])
    primary = parse_origins(os.environ['PUBLIC_URL'])[0]
    if primary not in origins:
        raise ValueError('PUBLIC_URL must be one of HOMELAB_PUBLIC_URLS')
    hashed = password_hash(os.environ) if args.auth_mode == 'basic' else None
    target = '/etc/caddy/Caddyfile.passthrough' if args.auth_mode == 'none' else '/etc/caddy/Caddyfile'
    Path(target).write_text(
        render(origins, os.environ.get('CADDY_TRUSTED_PROXIES', 'none') == 'none', args.auth_mode, hashed), encoding='utf-8')
    if hashed:
        # The unmodified upstream lifecycle validates this native hash input.
        print('bcrypt:' + hashed.split('$')[2] + ':' + hashed)


if __name__ == '__main__':
    main()
