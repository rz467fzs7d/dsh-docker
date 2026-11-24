import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('incremental', HERE / 'build_incremental.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class TargetBuildTests(unittest.TestCase):
    def test_reuses_workstation_but_rebuilds_verified_dsh_from_latest_source(self):
        source = (HERE.parent / 'image/Dockerfile').read_text()
        rendered = build.dockerfile(source)
        self.assertEqual(rendered.count('FROM ${BASE_IMAGE}'), 2)
        self.assertNotIn('FROM ${NODE_IMAGE}', rendered)
        self.assertNotIn('xcaddy build', rendered)
        self.assertNotIn('corepack enable', rendered)
        self.assertIn('ADD --checksum=sha256:${DSH_SOURCE_ARCHIVE_SHA256}', rendered)
        self.assertIn('CI=true pnpm install --frozen-lockfile', rendered)
        self.assertIn('CI=true pnpm run build:official', rendered)
        self.assertIn('RUN rm -rf /opt/dsh', rendered)
        self.assertIn('COPY --from=dsh-deps --chown=node:node /opt/dsh /opt/dsh', rendered)
        self.assertIn('node-pty/build/Release/pty.node', rendered)

    def test_base_version_environment_cannot_override_requested_new_release(self):
        rendered = build.dockerfile((HERE.parent / 'image/Dockerfile').read_text())
        self.assertIn('DSH_VERSION=${HOMELAB_DSH_VERSION}', rendered)
        self.assertIn('DSH_SOURCE_VERSION=${HOMELAB_DSH_VERSION}', rendered)
        self.assertIn('node -p process.versions.node', rendered)

    def test_unrecognized_upstream_builder_fails_for_review(self):
        source = (HERE.parent / 'image/Dockerfile').read_text().replace('RUN corepack enable', 'RUN another_manager enable')
        with self.assertRaisesRegex(ValueError, 'Upstream source-build command changed'):
            build.dockerfile(source)


if __name__ == '__main__':
    unittest.main()
