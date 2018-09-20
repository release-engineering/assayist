# SPDX-License-Identifier: GPL-3.0+

import os
import subprocess
import shutil

import koji

from assayist.processor.configuration import config
from assayist.processor.logging import log


def get_koji_session():
    """
    Generate a Koji session.

    :return: a Koji session
    :rtype: koji.ClientSession
    """
    profile = koji.get_profile_module(config.koji_profile)
    return koji.ClientSession(profile.config.server)


def _assert_command(cmd_name):
    """
    Ensure a command is installed and can be found using the paths in $PATH.

    :raises RuntimeError: if the command is not installed
    """
    if not shutil.which(cmd_name):
        raise RuntimeError(f'The command "{cmd_name}" is not installed and is required')


def download_build(build_identifier, output_dir):
    """
    Download the artifacts associated with a Koji build.

    :param str/int build_identifer: the string of the builds NVR or the integer of the build ID
    :param str output_dir: the path to download the the archives to
    :return: a list of paths to the downloaded archives
    :rtype: list
    """
    # Make sure the Koji command is installed
    _assert_command('koji')
    if not os.path.isdir(output_dir):
        raise RuntimeError(f'The passed in directory of "{output_dir}" does not exist')

    session = get_koji_session()
    build = session.getBuild(build_identifier)
    if not build:
        raise RuntimeError(f'The Koji build "{build_identifier}" does not exist')

    # There's no API for this, so it's better to just call the CLI directly
    cmd = ['koji', '--profile', config.koji_profile, 'download-build', str(build['id'])]
    build_type = None
    if build['task_id']:
        build_task = session.getTaskInfo(build['task_id'])
        if not build_task:
            raise RuntimeError('The Koji task "{0}" was not found'.format(build['task_id']))
        if build_task['method'] == 'maven':
            build_type = 'maven'
        elif build_task['method'] != 'build':
            raise RuntimeError('The Koji build type with build method "{0}" is unsupported'
                               .format(build_task['method']))
    elif (build['extra'] or {}).get('container_koji_task_id'):
        build_type = 'image'

    if build_type:
        cmd.append('--type')
        cmd.append(build_type)

    log.info(f'Downloading build {build["id"]} from Koji')
    p = subprocess.Popen(cmd, cwd=output_dir, stdout=subprocess.PIPE)
    # For some reason, any errors are streamed to stdout and not stderr
    output, _ = p.communicate()
    if p.returncode != 0:
        raise RuntimeError(f'The command "{" ".join(cmd)}" failed with: {output}')

    download_prefix = 'Downloading: '
    artifacts = []
    for line in output.decode('utf-8').strip().split('\n'):
        if line.startswith(download_prefix):
            file_path = os.path.join(output_dir, line.split(download_prefix)[-1])
            artifacts.append(file_path)
            log.info(f'Downloaded {os.path.split(file_path)[-1]}')

    return artifacts
