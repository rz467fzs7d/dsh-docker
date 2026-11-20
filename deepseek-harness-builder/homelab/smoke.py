#!/usr/bin/env python3
"""Disposable real-image checks for password auth, origins and persistent cookies."""
import argparse
from http.client import HTTPConnection
from http.cookies import SimpleCookie
import html
import json
from pathlib import Path
import re
import secrets
import shlex
import subprocess
import tempfile
import time
from urllib.parse import quote, urlencode, urljoin, urlsplit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='homelab/dsh:latest')
    args = parser.parse_args()
    name = 'dsh-homelab-smoke-' + secrets.token_hex(5)
    username, password = 'smoke-user', secrets.token_urlsafe(24)
    origins = ['http://lan.example.test:3080', 'http://zt.example.test:3080']
    def docker(*argv, check=True):
        return subprocess.run(['docker', *argv], check=check, text=True, capture_output=True)
    with tempfile.TemporaryDirectory(prefix='dsh-homelab-smoke-') as td:
        root = Path(td)
        (root / 'data').mkdir()
        env = root / 'runtime.env'
        env.write_text('\n'.join([
            'PUBLIC_URL=' + origins[0], 'HOMELAB_PUBLIC_URLS=' + ','.join(origins),
            'AUTH_USERNAME=' + username, 'AUTH_PASSWORD=' + password,
            'AUTH_COOKIE_INSECURE=true', 'AUTH_TOKEN_LIFETIME=2592000',
            'DSH_TRUSTED_HOSTS=lan.example.test:3080,zt.example.test:3080',
            'CADDY_TRUSTED_PROXIES=none', 'DSH_TELEMETRY_DISABLED=1']) + '\n')
        env.chmod(0o600)
        try:
            docker('run', '-d', '--name', name, '--network', 'bridge',
                   '--health-interval', '10m', '--memory', '2g', '--cpus', '2',
                   '-p', '127.0.0.1::8080', '-v', str(root / 'data') + ':/data',
                   '--env-file', str(env), args.image)
            info = json.loads(docker('inspect', name).stdout)[0]
            port = int(info['NetworkSettings']['Ports']['8080/tcp'][0]['HostPort'])
            flags = {}
            def request(origin, path='/', method='GET', jar=None, data=None, headers=None):
                target = urlsplit(origin)
                hdr = {'Host': target.netloc, **(headers or {})}
                if jar:
                    hdr['Cookie'] = '; '.join(k + '=' + v for k, v in jar.items())
                body = urlencode(data).encode() if data is not None else None
                if body is not None:
                    hdr['Content-Type'] = 'application/x-www-form-urlencoded'
                conn = HTTPConnection('127.0.0.1', port, timeout=15)
                conn.request(method, path, body=body, headers=hdr)
                response = conn.getresponse()
                response_headers = response.getheaders()
                text = response.read().decode('utf-8', errors='replace')
                status = response.status
                conn.close()
                for key, value in response_headers:
                    if key.lower() == 'set-cookie':
                        for k, v in SimpleCookie(value).items():
                            if jar is not None:
                                jar[k] = v.value
                            flags[k] = {'httponly': bool(v['httponly']),
                                        'secure': bool(v['secure']), 'maxage': v['max-age']}
                return status, dict((k.lower(), v) for k, v in response_headers), text
            def ready():
                deadline = time.monotonic() + 240
                while time.monotonic() < deadline:
                    try:
                        if request(origins[0], '/healthz')[0] == 200:
                            return
                    except (OSError, TimeoutError):
                        pass
                    time.sleep(2)
                raise AssertionError('DSH/Caddy did not become ready')
            def follow(origin, response, jar):
                for _ in range(10):
                    status, hdr, _ = response
                    if not 300 <= status < 400:
                        return response
                    target = urlsplit(urljoin(origin, hdr['location']))
                    assert target.scheme + '://' + target.netloc == origin, 'Redirect escaped request origin'
                    response = request(origin, target.path + ('?' + target.query if target.query else ''), jar=jar)
                raise AssertionError('Login redirect loop')
            def password_form(origin, jar):
                first = request(origin, jar=jar)
                assert first[0] == 302 and '/auth/' in first[1]['location']
                assert follow(origin, first, jar)[0] == 200
                step = request(origin, '/auth/login?redirect_url=' + quote(origin + '/', safe=''),
                               method='POST', jar=jar, data={'username': username, 'realm': 'local'})
                assert step[0] == 303, ('Username stage', step[0])
                page = follow(origin, step, jar)
                action = re.search(r'<form[^>]+action="([^"]+)"', page[2])
                sandbox = re.search(r'name="sandbox_id"[^>]+value="([^"]+)"', page[2])
                assert action and sandbox, 'Missing password form'
                return html.unescape(action.group(1)), sandbox.group(1)
            ready()
            imports = ('import sys,paramiko,yaml,requests,grpc,google.protobuf,PIL,mutagen,'
                       'websocket,msgpack; assert sys.prefix == "/opt/homelab-venv"')
            for argv in [('python3', '-c', imports),
                         ('bash', '-lc', 'python3 -c ' + shlex.quote(imports))]:
                docker('exec', '--user', 'node', name, *argv)
            print('PASS isolated Skill Python in direct and login shells', flush=True)
            assert request('http://evil.example:3080')[0] == 403
            good_jars = []
            for origin in origins:
                jar = {}
                action, sandbox = password_form(origin, jar)
                response = request(origin, action, 'POST', jar,
                                   {'secret': password, 'sandbox_id': sandbox, 'submit': 'Sign In'})
                assert response[0] == 303, ('Password stage', response[0])
                page = follow(origin, response, jar)
                assert page[0] == 200 and 'authentication required' not in page[2]
                assert 'DSH_ACCESS_TOKEN' in jar and any(k.startswith('dsh-auth-') for k in jar)
                assert request(origin, jar=jar)[0] == 200
                bad_origin = request(origin, '/api/settings/describe', 'POST', jar,
                                     headers={'Origin': 'http://evil.example'})
                assert bad_origin[0] == 403
                good_jars.append(jar)
                print('PASS password login, native bootstrap and Origin boundary: ' + origin, flush=True)
            assert flags['DSH_ACCESS_TOKEN']['httponly'], flags
            assert not flags['DSH_ACCESS_TOKEN']['secure'], flags
            assert flags['DSH_ACCESS_TOKEN']['maxage'] == '2592000', flags
            assert all(v['httponly'] for k, v in flags.items() if k.startswith('dsh-auth-'))
            bad = {}
            action, sandbox = password_form(origins[0], bad)
            request(origins[0], action, 'POST', bad,
                    {'secret': 'deliberately-wrong-password', 'sandbox_id': sandbox, 'submit': 'Sign In'})
            assert 'DSH_ACCESS_TOKEN' not in bad
            assert request(origins[0], jar=bad)[0] == 302
            docker('restart', name)
            ready()
            for origin, jar in zip(origins, good_jars):
                assert request(origin, jar=jar)[0] == 200
            print('PASS HttpOnly, 30-day cookie, wrong-password rejection and restart persistence', flush=True)
        except Exception:
            logs = docker('logs', name, check=False)
            safe = re.sub(r'([?&]token=)[A-Za-z0-9_-]+', r'\1[redacted]', logs.stdout + logs.stderr)
            print(safe[-3500:])
            raise
        finally:
            docker('rm', '-f', name, check=False)


if __name__ == '__main__':
    main()
