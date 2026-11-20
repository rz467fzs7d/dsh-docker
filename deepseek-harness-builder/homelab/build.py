#!/usr/bin/env python3
"""Resolve latest DSH on every build, then build the upstream workstation and adapter."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
BUILDER = HERE.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', default='homelab/dsh:latest')
    parser.add_argument('--platform', default='linux/amd64')
    parser.add_argument('--receipt', type=Path, default=Path('dsh-build-receipt.json'))
    args = parser.parse_args()
    def run(argv, **kwargs):
        return subprocess.run([str(a) for a in argv], check=True, **kwargs)
    revision = run(['git', '-C', HERE.parents[1], 'rev-parse', 'HEAD'],
                   text=True, capture_output=True).stdout.strip()
    with tempfile.TemporaryDirectory(prefix='dsh-homelab-build-') as td:
        context = Path(td) / 'image'
        shutil.copytree(BUILDER / 'image', context)
        source_file = context / 'dsh-source.json'
        run(['bash', BUILDER / 'scripts/resolve-dsh-source.sh', '--metadata-output', source_file,
             '--github-output', '/dev/null'])
        source = json.loads(source_file.read_text())
        run(['bash', BUILDER / 'scripts/prepare-dsh-version.sh', '--image-dir', context,
             '--version', source['version'], '--github-output', '/dev/null'])
        output = run(['python3', BUILDER / 'scripts/component-inputs.py', '--image-dir', context,
                      '--format', 'json'], text=True, capture_output=True)
        inputs = json.loads(output.stdout)
        command = ['docker', 'build', '--pull', '--platform', args.platform, '--target', 'workstation',
                   '-t', 'homelab/dsh-upstream:build']
        for key, value in inputs.items():
            command += ['--build-arg', key + '=' + value]
        run([*command, context])
        run(['docker', 'build', '--platform', args.platform, '--build-arg',
             'BASE_IMAGE=homelab/dsh-upstream:build', '--build-arg', 'SOURCE_REVISION=' + revision,
             '--build-arg', 'DSH_VERSION=' + source['version'], '-t', args.tag, HERE])
        image = json.loads(run(['docker', 'image', 'inspect', args.tag], text=True,
                               capture_output=True).stdout)[0]
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps({'image': args.tag, 'id': image['Id'],
                                           'platform': args.platform, 'revision': revision,
                                           'dsh': source}, indent=2) + '\n')


if __name__ == '__main__':
    main()
