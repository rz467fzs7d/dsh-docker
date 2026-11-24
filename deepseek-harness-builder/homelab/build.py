#!/usr/bin/env python3
"""Install the newest official npm DSH release directly on the Docker host."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-image', default='homelab/dsh:latest')
    p.add_argument('--tag', default='homelab/dsh:upgrade')
    p.add_argument('--platform', default='linux/amd64')
    p.add_argument('--receipt', type=Path, default=Path('dsh-build-receipt.json'))
    args = p.parse_args()
    def run(argv, **kw):
        return subprocess.run([str(a) for a in argv], check=True, **kw)
    base = json.loads(run(['docker', 'image', 'inspect', args.base_image], text=True, capture_output=True).stdout)[0]
    base_id = base['Id']
    base_ref = 'homelab/dsh-build-base:' + base_id.split(':')[-1]
    run(['docker', 'tag', base_id, base_ref])
    with tempfile.TemporaryDirectory(prefix='dsh-package-build-') as td:
        context = Path(td) / 'homelab'
        shutil.copytree(HERE, context, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        helper = ['docker', 'run', '--rm', '--network', 'bridge', '--no-healthcheck',
                  '--memory', '512m', '--cpu-shares', '128', '-v', str(HERE.parents[1]) + ':/source:ro',
                  '-v', td + ':/build', '--entrypoint', 'bash', base_id]
        revision = run([*helper, '-c', 'git -c safe.directory=/source -C /source rev-parse HEAD'], text=True, capture_output=True).stdout.strip()
        resolve = '''set -euo pipefail
version="$(npm view @deepseek-ai/dsh versions --json --prefer-online --registry=https://registry.npmjs.org | node /source/deepseek-harness-builder/scripts/resolve-latest-npm-version.mjs)"
npm view "@deepseek-ai/dsh@${version}" --json --prefer-online --registry=https://registry.npmjs.org > /build/npm-release.json
'''
        run([*helper, '-c', resolve])
        metadata = json.loads((Path(td) / 'npm-release.json').read_text())
        version = metadata['version'];integrity = metadata['dist']['integrity']
        print(json.dumps({'version': version, 'integrity': integrity, 'engines': metadata.get('engines')}), flush=True)
        run(['docker', 'build', '--platform', args.platform, '-f', context / 'Dockerfile.package',
             '--build-arg', 'BASE_IMAGE=' + base_ref, '--build-arg', 'SOURCE_REVISION=' + revision,
             '--build-arg', 'HOMELAB_DSH_VERSION=' + version,
             '--build-arg', 'HOMELAB_DSH_INTEGRITY=' + integrity, '-t', args.tag, context])
        image = json.loads(run(['docker', 'image', 'inspect', args.tag], text=True, capture_output=True).stdout)[0]
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps({'image': args.tag, 'id': image['Id'], 'configDigest': image['Id'],
                                           'platform': args.platform, 'revision': revision, 'baseImage': base_id,
                                           'buildMode': 'target-host-npm', 'dsh': {'version': version,
                                           'package': '@deepseek-ai/dsh', 'tarball': metadata['dist']['tarball'],
                                           'integrity': integrity, 'engines': metadata.get('engines')}}, indent=2) + '\n')


if __name__ == '__main__':
    main()
