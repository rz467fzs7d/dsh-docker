import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('homelab_config', HERE / 'configure.py')
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


class ConfigurationTests(unittest.TestCase):
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
