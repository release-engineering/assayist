# SPDX-License-Identifier: GPL-3.0+

import json
import os
import shutil
import subprocess
import tarfile
import zipfile
import re

import koji

from assayist.processor.configuration import config
from assayist.processor.logging import log
from assayist.processor.error import BuildSourceNotFound, BuildTypeNotSupported


def get_koji_session():  # pragma: no cover
    """
    Generate a Koji session.

    :return: a Koji session
    :rtype: koji.ClientSession
    """
    profile = koji.get_profile_module(config.koji_profile)
    return koji.ClientSession(profile.config.server)


def assert_command(cmd_name):
    """
    Ensure a command is installed and can be found using the paths in $PATH.

    :raises RuntimeError: if the command is not installed
    """
    if not shutil.which(cmd_name):
        raise RuntimeError(f'The command "{cmd_name}" is not installed and is required')


def write_file(data, in_dir, in_file):
    """
    Write the data to the specified JSON file.

    :param dict/list data: the data to write out to JSON. Must be serializable.
    :param str in_file: The name of the input file to read. Probably one of the class constants.
    :param str in_dir: The directory the file is in.
    """
    with open(os.path.join(in_dir, in_file), 'w') as f:
        json.dump(data, f)


def get_build_type(build_info, task_info):
    """Use heuristics to determine the type of this build.

    :param build_info: the dict representing the Koji build to analyze
    :param task_info: the dict representing the Koji task to analyze
    :return: build type
    :rtype: str
    """
    # If this build has an associated task, return it's method as the build type.
    if task_info:
        return task_info['method']

    # Check if the build defines extra attributes.
    extra = build_info.get('extra')
    if not extra or not isinstance(extra, dict):
        return None

    # Check if this is a container build.
    if extra.get('container_koji_task_id'):
        return 'buildContainer'

    # Check if this is a PNC maven build.
    if extra.get('maven'):
        return 'maven'

    # Check if this is a module build.
    typeinfo = extra.get('typeinfo')
    if typeinfo and typeinfo.get('module'):
        return 'module'


def download_build_data(build_identifier, output_dir='/metadata'):
    """
    Download the JSON data associated with a build.

    :param str/int build_identifier: the string of the builds NVR or the integer of the build ID
    :param str output_dir: the path to download the brew info to
    :raises BuildSourceNotFound: when the source can't be determined
    :return: build information
    :rtype: dict
    :raises BuildTypeNotSupported: when the build type is not supported for analysis
    """
    # Import this here to avoid a circular import
    from assayist.processor.base import Analyzer
    # Make sure the Koji command is installed
    assert_command('koji')
    koji_session = get_koji_session()
    build = koji_session.getBuild(build_identifier)
    if not build.get('source'):
        # Sometimes there is no source url on the build but it can be found in the task
        # request info instead. Try looking there, and if found update the build info
        # so the analyzers have a nice consistent place to find it.
        build['source'] = get_source_of_build(build)

    # Get task info
    task = None
    if 'task_id' in build and build['task_id']:
        task = koji_session.getTaskInfo(build['task_id'])
        write_file(task, output_dir, Analyzer.TASK_FILE)

    # Determine the build type and add it to build metadata so that analyzers can easily fetch it
    # without having to perform the heuristic below themselves.
    build_type = get_build_type(build, task)
    build['type'] = build_type
    write_file(build, output_dir, Analyzer.BUILD_FILE)

    # Exit early if the type of this build is not supported since none of the analyzers will do
    # anything meaningful with the data downloaded below anyway.
    if build_type not in Analyzer.SUPPORTED_BUILD_TYPES:
        raise BuildTypeNotSupported(
            f'Build {build_identifier} type "{build_type}" is not supported for analysis')

    # Get maven info
    maven = koji_session.getMavenBuild(build_identifier)
    if maven:
        write_file(maven, output_dir, Analyzer.MAVEN_FILE)

    # Get list of RPMs
    rpms = koji_session.listRPMs(build_identifier)
    if rpms:
        write_file(rpms, output_dir, Analyzer.RPM_FILE)

    # Get list of archives
    archives = koji_session.listArchives(build_identifier)
    if archives:
        write_file(archives, output_dir, Analyzer.ARCHIVE_FILE)

    # Get list of RPMs in each image
    image_rpms = {}
    for archive in archives:
        if 'btype' in archive and archive['btype'] == 'image':
            aid = archive['id']
            image_rpms[aid] = koji_session.listRPMs(imageID=aid)

    if image_rpms:
        write_file(image_rpms, output_dir, Analyzer.IMAGE_RPM_FILE)

    # Get list of RPMs in the buildroots
    buildroot_ids = set()
    for artifact in rpms + archives:
        bid = artifact['buildroot_id']
        if bid:
            buildroot_ids.add(bid)

    buildroot_components = {}
    for bid in sorted(buildroot_ids):
        buildroot_components[bid] = [c['rpm_id'] for c in koji_session.getBuildrootListing(bid)]

    for bid, rpm_ids in buildroot_components.items():
        # getBuildrootListing() does not provide full RPM information to be able to create an
        # artifact so call getRPM on each of the RPMs in a single call to get it.
        koji_session.multicall = True
        for rpm_id in rpm_ids:
            koji_session.getRPM(rpm_id)

        rpm_infos = koji_session.multiCall()
        buildroot_components[bid] = [rpm_info[0] for rpm_info in rpm_infos]

    if buildroot_components:
        write_file(buildroot_components, output_dir, Analyzer.BUILDROOT_FILE)

    return build


def download_build(build_info, output_dir):
    """
    Download the artifacts associated with a Koji build.

    :param dict build_info: the build information from koji
    :param str output_dir: the path to download the archives to
    :return: a list of downloaded artifacts
    :rtype: list
    """
    # Make sure the Koji command is installed
    assert_command('koji')
    if not os.path.isdir(output_dir):
        raise RuntimeError(f'The passed in directory of "{output_dir}" does not exist')

    if not build_info:
        raise RuntimeError(f'The Koji build cannot be None')

    # There's no API for this, so it's better to just call the CLI directly
    cmd = ['koji', '--profile', config.koji_profile, 'download-build', str(build_info['id'])]

    # Because builds may contain artifacts of different types (e.g. RPMs as well as JARs),
    # cycle through all types of artifacts: RPMs (default), Maven archives (--type maven),
    # and container images (--type image); purposefully ignoring Windows builds for now (--type
    # win).
    build_type_opts = ([], ['--type', 'maven'], ['--type', 'image'])

    log.info(f'Downloading build {build_info["id"]} from Koji')
    download_prefix = 'Downloading: '
    artifacts = []

    for build_type in build_type_opts:
        download_cmd = cmd + build_type
        p = subprocess.Popen(download_cmd, cwd=output_dir, stdout=subprocess.PIPE)

        # For some reason, any errors are streamed to stdout and not stderr
        output, _ = p.communicate()
        output = output.decode('utf-8')
        if p.returncode != 0:
            if 'No' in output and 'available' in output:
                continue
            raise RuntimeError(f'The command "{" ".join(cmd)}" failed with: {output}')

        for line in output.strip().split('\n'):
            if line.startswith(download_prefix):
                file_path = os.path.join(output_dir, line.split(download_prefix)[-1].lstrip('/'))
                artifacts.append(file_path)
                log.info(f'Downloaded {os.path.split(file_path)[-1]}')

    return artifacts


def get_source_of_build(build_info):
    """
    Find the source used to build the Koji build.

    :param dict build_info: the dict representing the Koji build to analyze
    :return: the source used by Koji to build the build
    :rtype: str
    :raises BuildSourceNotFound: when the source can't be determined
    """
    no_source_msg = f'Build {build_info["id"]} has no associated source URL'
    if build_info.get('source'):
        return build_info['source']

    elif build_info.get('task_id') is None:
        raise BuildSourceNotFound(no_source_msg)

    task_request = get_koji_session().getTaskRequest(build_info['task_id'])
    if task_request is None:
        raise BuildSourceNotFound(no_source_msg)
    elif not isinstance(task_request, list):
        raise BuildSourceNotFound(no_source_msg)

    for value in task_request:
        # Check if the value in the task_request is a git URL
        if isinstance(value, str) and re.match(r'git\+?(http[s]?|ssh)?://', value):
            return value
        # Look for a dictionary in the task_request that may include certain keys that hold the URL
        elif isinstance(value, dict):
            if isinstance(value.get('ksurl'), str):
                return value['ksurl']
            elif isinstance(value.get('indirection_template_url'), str):
                return value['indirection_template_url']

    raise BuildSourceNotFound(no_source_msg)


def download_source(build_info, output_dir, sources_cmd=None):
    """
    Download the source (from dist-git) that was used in the specified build.

    :param dict build_info: build information from koji.getBuild()
    :param str output_dir: the path to download the source to
    :param list sources_cmd: command to run to download source artifacts,
        or None for the default (['rhpkg', 'sources'])
    """
    if sources_cmd is None:
        sources_cmd = ['rhpkg', '--user=1001', 'sources']

    # Make sure the commands we'll run are installed
    assert_command('git')
    assert_command(sources_cmd[0])

    # Certain URLs specified in the build's Source field do not specify a correct
    # combination of protocols that Git understands.
    source_url = re.sub(r'^git\+http', r'http', build_info['source'])
    log.info(f'Cloning source for {build_info["id"]}')

    url, _, commit_id = source_url.partition('#')
    # Sometimes the source URL includes a "?" with an optional identifier; strip this so we're
    # left with a bare URL.
    url = url.split('?', 1)[0]
    cmd = ['git', 'clone', url, output_dir]
    process = subprocess.Popen(cmd, cwd=output_dir,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    _, error_output = process.communicate()
    error_output = error_output.decode('utf-8')
    if process.returncode != 0:
        raise RuntimeError(f'The command "{" ".join(cmd)}" failed with: {error_output}')

    cmd = ['git', 'reset', '--hard', commit_id]
    process = subprocess.Popen(cmd, cwd=output_dir,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    _, error_output = process.communicate()
    error_output = error_output.decode('utf-8')
    if process.returncode != 0:
        raise RuntimeError(f'The command "{" ".join(cmd)}" failed with: {error_output}')

    log.info(f'Downloading sources for {build_info["id"]}')
    process = subprocess.Popen(sources_cmd, cwd=output_dir,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    _, error_output = process.communicate()
    error_output = error_output.decode('utf-8')
    if process.returncode != 0:
        raise RuntimeError(f'The command "{" ".join(cmd)}" failed with: {error_output}')


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
    assert_command('rpm2cpio')
    assert_command('cpio')

    # Get the CPIO file
    cpio_file = _rpm_to_cpio(rpm_file)
    # Unpack the CPIO file
    _unpack_cpio(cpio_file, output_dir)
    log.info(f'Successfully unpacked {os.path.split(rpm_file)[-1]} to {output_dir}')


def unpack_container_image(container_image_file, output_dir):
    """
    Unpack a container image to the specified directory.

    :param str container_image_file: the path to the container image file to unpack
    :param str output_dir: the path to unpack the container image to
    """
    # Unpack the manifest.json file from which we figure out the latest image layer
    with tarfile.open(container_image_file) as tar:
        manifest_file = tar.extractfile('manifest.json')
        manifest_data = json.loads(manifest_file.read().decode('utf-8'))
        layer_to_unpack = manifest_data[0]['Layers'][-1]

        # Unpack the last layer, which itself is a .tar file
        tar.extract(layer_to_unpack)

    # Extract the file system contents from the last layer
    with tarfile.open(layer_to_unpack) as tar:
        tar.extractall(output_dir)

    # Remove extracted layer .tar file
    shutil.rmtree(os.path.split(layer_to_unpack)[0])

    log.info(f'Successfully unpacked {container_image_file} to {output_dir}')


def unpack_zip(zip_file, output_dir):  # pragma: no cover
    """
    Unpack a ZIP-like archive file to the specified directory.

    :param str zip_file: the path to the archive file to unpack
    :param str output_dir: the path to unpack the archive to
    """
    with zipfile.ZipFile(zip_file) as zip_:
        zip_.extractall(output_dir)

    log.info(f'Successfully unpacked {zip_file} to {output_dir}')


def unpack_tar(tar_file, output_dir):  # pragma: no cover
    """
    Unpack a TAR-like archive file to the specified directory.

    :param str tar_file: the path to the archive file to unpack
    :param str output_dir: the path to unpack the archive to
    """
    with tarfile.open(tar_file) as tar:
        tar.extractall(output_dir)

    log.info(f'Successfully unpacked {tar_file} to {output_dir}')


def unpack_artifacts(artifacts, output_dir):
    """
    Unpack a list of artifacts to the specified directory.

    :param list artifacts: a list of paths to artifacts to unpack
    :param str output_dir: a path to a directory to unpack the artifacts
    """
    if output_dir and not os.path.isdir(output_dir):
        raise RuntimeError(f'The passed in directory of "{output_dir}" does not exist')

    for artifact in artifacts:
        if not os.path.isfile(artifact):
            raise RuntimeError(f'The artifact "{artifact}" could not be found')

        artifact_filename = os.path.split(artifact)[-1]
        log.info(f'Unpacking {artifact_filename}')

        if artifact_filename.startswith('docker-image') and artifact_filename.endswith('.tar.gz'):
            output_subdir = os.path.join(output_dir, 'container_layer', artifact_filename)
            os.makedirs(output_subdir)
            unpack_container_image(artifact, output_subdir)

        elif artifact_filename.endswith('.rpm'):
            output_subdir = os.path.join(output_dir, 'rpm', artifact_filename)
            os.makedirs(output_subdir)
            unpack_rpm(artifact, output_subdir)

        elif zipfile.is_zipfile(artifact):
            output_subdir = os.path.join(output_dir, 'non-rpm', artifact_filename)
            os.makedirs(output_subdir)
            unpack_zip(artifact, output_subdir)

        elif tarfile.is_tarfile(artifact):
            output_subdir = os.path.join(output_dir, 'non-rpm', artifact_filename)
            os.makedirs(output_subdir)
            unpack_tar(artifact, output_subdir)

        else:
            # Files such as .pom do not need to be unpacked, others such as .gem are not yet
            # supported.
            log.info(f'Skipping unpacking (unsupported archive type or not an archive): {artifact}')
            continue
