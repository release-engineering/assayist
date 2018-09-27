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

    :param str/int build_identifier: the string of the builds NVR or the integer of the build ID
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

    # Because builds may contain artifacts of different types (e.g. RPMs as well as JARs),
    # cycle through all types of artifacts: RPMs (default), Maven archives (--type maven),
    # and container images (--type image); purposefully ignoring Windows builds for now (--type
    # win).
    build_type_opts = ([], ['--type', 'maven'], ['--type', 'image'])

    log.info(f'Downloading build {build["id"]} from Koji')
    download_prefix = 'Downloading: '
    artifacts = []

    for build_type in build_type_opts:
        download_cmd = cmd + build_type
        p = subprocess.Popen(download_cmd, cwd=output_dir, stdout=subprocess.PIPE)

        # For some reason, any errors are streamed to stdout and not stderr
        output, _ = p.communicate()
        output = output.decode('utf-8')
        if p.returncode != 0 and 'available' not in output:
            raise RuntimeError(f'The command "{" ".join(cmd)}" failed with: {output}')

        for line in output.strip().split('\n'):
            if line.startswith(download_prefix):
                file_path = os.path.join(output_dir, line.split(download_prefix)[-1])
                artifacts.append(file_path)
                log.info(f'Downloaded {os.path.split(file_path)[-1]}')

    return artifacts


def _rpm_to_cpio(rpm_file):
    """
    Convert an RPM file to a CPIO file.

    :path str rpm_file: the path to the RPM file to convert
    :return: the bytes of the CPIO file
    :rtype: bytes
    """
    # Convert the RPM to a CPIO file
    rpm2cpio_cmd = ['rpm2cpio', rpm_file]
    rpm2cpio = subprocess.Popen(rpm2cpio_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    cpio_file, errors = rpm2cpio.communicate()
    if rpm2cpio.returncode != 0:
        raise RuntimeError(
            f'The command "{" ".join(rpm2cpio_cmd)}" failed with: {errors.decode("utf-8")}')
    return cpio_file


def _unpack_cpio(cpio_file, output_dir):
    """
    Unpack CPIO file bytes.

    :param bytes cpio_file: the CPIO file to unpack
    """
    cpio_cmd = ['cpio', '-idmv']
    cpio = subprocess.Popen(
        cpio_cmd, cwd=output_dir, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    _, errors = cpio.communicate(input=cpio_file)
    if cpio.returncode != 0:
        raise RuntimeError(
            f'The command "{" ".join(cpio_cmd)}" failed with: {errors.decode("utf-8")}')


def unpack_rpm(rpm_file, output_dir):
    """
    Unpack the RPM file to the specified directory.

    :param str rpm_file: the path to the RPM to unpack
    :param str output_dir: the path to unpack the RPM to
    """
    _assert_command('rpm2cpio')
    _assert_command('cpio')

    # Get the CPIO file
    cpio_file = _rpm_to_cpio(rpm_file)
    # Unpack the CPIO file
    _unpack_cpio(cpio_file, output_dir)
    log.info(f'Successfully unpacked {os.path.split(rpm_file)[-1]} to {output_dir}')


def unpack_artifacts(artifacts, output_dir):
    """
    Unpack a list of artifacts to the specified directory.

    :param list artifacts: a list of paths to artifacts to unpack
    "param str output_dir: a path to a directory to unpack the artifacts
    """
    if output_dir and not os.path.isdir(output_dir):
        raise RuntimeError(f'The passed in directory of "{output_dir}" does not exist')

    for artifact in artifacts:
        if not os.path.isfile(artifact):
            raise RuntimeError(f'The artifact "{artifact}" could not be found')

        log.info(f'Unpacking {os.path.split(artifact)[-1]}')
        # Create a subdirectory to store the unpacked artifact
        output_subdir = os.path.join(output_dir, os.path.split(artifact)[-1])
        if not os.path.isdir(output_subdir):
            os.mkdir(output_subdir)

        extension = os.path.splitext(artifact)[-1]
        if extension == '.rpm':
            unpack_rpm(artifact, output_subdir)
        else:
            raise RuntimeError(f'"{artifact}" is not a supported file type to unpack')
