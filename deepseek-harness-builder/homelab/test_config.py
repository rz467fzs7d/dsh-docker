import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('homelab_config', HERE / 'configure.py')
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


class ConfigurationTests(unittest.TestCase):
    def test_basic_auth_replaces_portal_and_protects_every_application_route(self):
        hashed = '$2b$12$' + 'a' * 53
        rendered = config.render(['http://nas:3080'], direct=True, auth_mode='basic', hashed=hashed)
        self.assertIn('basic_auth @dsh_basic_required bcrypt DSH', rendered)
        self.assertIn('{$AUTH_USERNAME} ' + hashed, rendered)
        self.assertNotIn('authentication portal', rendered)
        self.assertNotIn('authorize with', rendered)
        self.assertNotIn('@@', rendered)
        self.assertEqual(rendered.count('import dsh_basic'), 4)
        self.assertIn('header_up -Authorization', rendered)
        self.assertIn('rewrite @dsh_bootstrap /?token={$DSH_LAUNCH_TOKEN}', rendered)
        self.assertIn('route /healthz', rendered)
        self.assertEqual(rendered.count('route /healthz'), 1)

    def test_only_native_mux_upgrade_uses_native_signed_cookie_auth(self):
        rendered = config.render(['http://nas:3080'], True, 'basic', '$2b$12$' + 'a' * 53)
        self.assertIn('method GET\n            path /api/remote.mux\n            header Upgrade websocket', rendered)
        self.assertNotIn('Cookie *dsh-auth-*\n        }', rendered)
        self.assertIn('respond @unexpected_origin "Forbidden" 403', rendered)
        portal = config.render(['http://nas:3080'], True)
        self.assertNotIn('@dsh_basic_required', portal)
        self.assertIn('authorize with dsh_policy', portal)

    def test_plaintext_password_uses_stdin_not_process_arguments(self):
        hashed = '$2b$12$' + 'a' * 53
        with patch.object(config.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, hashed + '\n')) as run:
            self.assertEqual(config.password_hash({'AUTH_PASSWORD': 'test-only-password'}), hashed)
        self.assertNotIn('test-only-password', run.call_args.args[0])
        self.assertEqual(run.call_args.kwargs['input'], 'test-only-password\n')

    def test_rejects_ambiguous_weak_or_control_character_credentials(self):
        for env in [{}, {'AUTH_PASSWORD': 'short'}, {'AUTH_PASSWORD': 'valid-password\n'},
                    {'AUTH_PASSWORD': 'test-only-password', 'AUTH_PASSWORD_HASH': 'hash'},
                    {'AUTH_PASSWORD_HASH': 'bcrypt:12:$2b$11$' + 'a' * 53}]:
            with self.subTest(env=list(env)), self.assertRaises(ValueError):
                config.password_hash(env)

    def test_both_origins_share_password_login_but_keep_origin_boundary(self):
        origins = config.parse_origins('http://192.168.0.10:3080/,http://172.16.0.10:3080')
        rendered = config.render(origins, direct=True)
        for host in ['192.168.0.10:3080', '172.16.0.10:3080']:
            self.assertIn('domain exact "' + host + '" path prefix /', rendered)
        self.assertIn('["http://192.168.0.10:3080", "http://172.16.0.10:3080"]', rendered)
        self.assertIn('respond @untrusted_host "Forbidden" 403', rendered)
        self.assertIn('respond @unexpected_origin "Forbidden" 403', rendered)
        self.assertIn('request_header -X-Forwarded-Proto', rendered)
        self.assertNotIn('@@', rendered)

    def test_http_does_not_remove_httponly(self):
        rendered = config.render(['http://192.168.0.10:3080'], direct=True)
        self.assertIn('Set-Cookie "[;[:space:]]*$" "; HttpOnly"', rendered)
        self.assertIn('defer', rendered)
        self.assertIn('cookie insecure {$AUTH_COOKIE_INSECURE}', rendered)

    def test_external_https_proxy_keeps_forwarding_headers(self):
        rendered = config.render(['https://dsh.example.com'], direct=False)
        self.assertNotIn('request_header -X-Forwarded-Proto', rendered)

    def test_rejects_injection_credentials_paths_and_mixed_transports(self):
        for value in ['http://user:password@host', 'http://host/path', 'http://host/?token=x',
                      'http://host/#fragment', 'http://host\nrespond 200', 'ftp://host',
                      'http://host:99999', 'http://host,,http://other',
                      'http://host,https://other', 'http://*.example.com']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                config.parse_origins(value)

    def test_duplicate_origins_normalize_and_deduplicate(self):
        self.assertEqual(config.parse_origins('http://HOST:3080/,http://host:3080'), ['http://host:3080'])


if __name__ == '__main__':
    unittest.main()
