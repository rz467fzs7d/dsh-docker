import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('homelab_build', HERE / 'build_source.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class BuildTests(unittest.TestCase):
    def fixture(self, root):
        builder = root / 'builder'
        (builder / 'image').mkdir(parents=True)
        (builder / 'image/dsh-source.json').write_text('{"version":"0.0.1"}')
        return builder

    def test_each_build_resolves_latest_instead_of_committed_baseline(self):
        calls = []
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            builder = self.fixture(root)
            receipt = root / 'receipt.json'
            def run(argv, **kwargs):
                calls.append(argv)
                if argv[0] == 'git':
                    return subprocess.CompletedProcess(argv, 0, 'a' * 40)
                if 'resolve-dsh-source.sh' in argv[1]:
                    self.assertNotIn('--version', argv)
                    dest = Path(argv[argv.index('--metadata-output') + 1])
                    dest.write_text(json.dumps({'version': '9.9.9', 'commit': 'b' * 40}))
                if 'component-inputs.py' in argv[1]:
                    return subprocess.CompletedProcess(argv, 0, '{"DSH_VERSION":"9.9.9"}')
                if argv[:3] == ['docker', 'image', 'inspect']:
                    return subprocess.CompletedProcess(argv, 0, '[{"Id":"sha256:fixture"}]')
                return subprocess.CompletedProcess(argv, 0, '')
            with patch.object(build, 'BUILDER', builder), patch.object(build.subprocess, 'run', side_effect=run), \
                    patch.object(sys, 'argv', ['build.py', '--receipt', str(receipt)]):
                build.main()
            builds = [c for c in calls if c[:2] == ['docker', 'build']]
            self.assertEqual(len(builds), 2)
            self.assertIn('--pull', builds[0])
            self.assertIn('DSH_VERSION=9.9.9', builds[0])
            self.assertIn('DSH_VERSION=9.9.9', builds[1])
            self.assertEqual(json.loads(receipt.read_text())['dsh']['version'], '9.9.9')

    def test_resolution_failure_never_falls_back_to_old_source(self):
        calls = []
        with tempfile.TemporaryDirectory() as td:
            builder = self.fixture(Path(td))
            def run(argv, **kwargs):
                calls.append(argv)
                if argv[0] == 'git':
                    return subprocess.CompletedProcess(argv, 0, 'a' * 40)
                raise subprocess.CalledProcessError(22, argv)
            with patch.object(build, 'BUILDER', builder), patch.object(build.subprocess, 'run', side_effect=run), \
                    patch.object(sys, 'argv', ['build.py']), self.assertRaises(subprocess.CalledProcessError):
                build.main()
            self.assertFalse(any(c[0] == 'docker' for c in calls))


if __name__ == '__main__':
    unittest.main()
