#!/usr/bin/env python3
"""Build latest DSH on the target Docker host, reusing its workstation toolchain."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
BUILDER = HERE.parent


def dockerfile(upstream):
    stage = upstream.split('FROM ${NODE_IMAGE} AS dsh-deps\n', 1)[1].split('\nFROM ${NODE_IMAGE} AS pnpm-bundle', 1)[0]
    declarations = stage.split('\nENV PYTHON=', 1)[0]
    commands = stage[stage.index('WORKDIR /opt/dsh'):]
    original = 'RUN corepack enable \\\n    && corepack prepare "pnpm@${PNPM_VERSION}" --activate \\\n'
    if commands.count(original) != 1:
        raise ValueError('Upstream source-build command changed; review it before updating')
    commands = commands.replace(original, 'RUN test "$(pnpm --version)" = "${HOMELAB_PNPM_VERSION}" \\\n')
    return '''# syntax=docker/dockerfile:1
ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS dsh-deps
''' + declarations + '''
ARG HOMELAB_DSH_VERSION
ARG HOMELAB_NODE_VERSION
ARG HOMELAB_PNPM_VERSION
ENV DSH_VERSION=${HOMELAB_DSH_VERSION} DSH_SOURCE_VERSION=${HOMELAB_DSH_VERSION}
ENV PYTHON=/usr/local/bin/python3
RUN test "$(node -p process.versions.node)" = "${HOMELAB_NODE_VERSION}" \\
    && rm -rf /opt/dsh && mkdir -p /opt/dsh
''' + commands + '''
FROM ${BASE_IMAGE} AS workstation
ARG HOMELAB_DSH_VERSION
ARG SOURCE_REVISION
ARG DSH_SOURCE_COMMIT
ENV DSH_VERSION=${HOMELAB_DSH_VERSION}
LABEL org.opencontainers.image.source="https://github.com/rz467fzs7d/dsh-docker" \\
      org.opencontainers.image.version="${HOMELAB_DSH_VERSION}" \\
      org.opencontainers.image.revision="${SOURCE_REVISION}" \\
      io.homelab.dsh.source-commit="${DSH_SOURCE_COMMIT}"
RUN rm -rf /opt/dsh
COPY --from=dsh-deps --chown=node:node /opt/dsh /opt/dsh
COPY --chmod=0755 homelab/entrypoint.sh /opt/homelab/entrypoint.sh
COPY homelab/configure.py homelab/Caddyfile.template homelab/auth-portal.Caddyfile homelab/auth-routes.Caddyfile /opt/homelab/
COPY homelab/profile.sh /etc/profile.d/zz-homelab-tools.sh
'''


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
    # Use an immutable local base throughout the build and keep the running tag intact.
    base_id = base['Id']
    with tempfile.TemporaryDirectory(prefix='dsh-target-build-') as td:
        context = Path(td) / 'image'
        shutil.copytree(BUILDER / 'image', context)
        shutil.copytree(HERE, context / 'homelab', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        helper = ['docker', 'run', '--rm', '--network', 'bridge', '--no-healthcheck',
                  '--memory', '512m', '--cpu-shares', '128',
                  '-v', str(HERE.parents[1]) + ':/source:ro', '-v', td + ':/build',
                  '--entrypoint', 'bash', base_id]
        revision = run([*helper, '-c', 'git -c safe.directory=/source -C /source rev-parse HEAD'],
                       text=True, capture_output=True).stdout.strip()
        scripts = '/source/deepseek-harness-builder/scripts/'
        run([*helper, scripts + 'resolve-dsh-source.sh', '--metadata-output',
             '/build/image/dsh-source.json', '--github-output', '/dev/null'])
        source = json.loads((context / 'dsh-source.json').read_text())
        run([*helper, scripts + 'prepare-dsh-version.sh', '--image-dir', '/build/image',
             '--version', source['version'], '--github-output', '/dev/null'])
        inputs = json.loads(run(['python3', BUILDER / 'scripts/component-inputs.py', '--image-dir',
                                 context, '--format', 'json'], text=True, capture_output=True).stdout)
        (context / 'Dockerfile').write_text(dockerfile((context / 'Dockerfile').read_text()))
        command = ['docker', 'build', '--platform', args.platform, '--target', 'workstation',
                   '-t', args.tag, '--build-arg', 'BASE_IMAGE=' + base_id,
                   '--build-arg', 'SOURCE_REVISION=' + revision,
                   '--build-arg', 'HOMELAB_DSH_VERSION=' + source['version'],
                   '--build-arg', 'HOMELAB_NODE_VERSION=' + inputs['NODE_VERSION'],
                   '--build-arg', 'HOMELAB_PNPM_VERSION=' + inputs['PNPM_VERSION']]
        for key, value in inputs.items():
            command += ['--build-arg', key + '=' + value]
        run([*command, context])
        image = json.loads(run(['docker', 'image', 'inspect', args.tag], text=True, capture_output=True).stdout)[0]
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps({'image': args.tag, 'id': image['Id'],
                                           'configDigest': image['Id'], 'platform': args.platform,
                                           'revision': revision, 'baseImage': base_id,
                                           'buildMode': 'target-host-incremental', 'dsh': source}, indent=2) + '\n')


if __name__ == '__main__':
    main()
