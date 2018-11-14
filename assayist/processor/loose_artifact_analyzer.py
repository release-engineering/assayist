# SPDX-License-Identifier: GPL-3.0+

import glob
import os

from itertools import zip_longest
from hashlib import md5

from assayist.common.models import content
from assayist.processor.base import Analyzer
from assayist.processor.logging import log


class LooseArtifactAnalyzer(Analyzer):
    """
    Analyze RPMs/jars/similar that are embedded in the build artifacts.

    RPMs we have to treat differently from other artifact types because Koji treats them
    differently and there is no way to look up an rpm by checksum in the Koji api. So,
    for RPMs we will look them up by filename, which should be uniquely identifying across
    a single Koji instance (assuming someone hasn't renamed the file).

    The intention for other artifact types (jar, pom, etc) is that we will checksum them
    and then look them up in koji by checksum. You can accomplish the same thing with
    koji-build-finder, but for our use-case doing it outselves was just as easy and made
    dependency management and debugging a lot simpler.
    """

    FILE_EXTENSIONS = ['rpm', 'zip', 'tar', 'tar.gz', 'tar.bz2', 'tar.xz', 'rar', 'ear',
                       'jar', 'war', 'sar', 'kar', 'pom.xml', 'pom', 'war', 'jdocbook',
                       'jdocbook-style', 'plugin']
    KOJI_BATCH_SIZE = 10

    def run(self):
        """Start the loose RPM analyzer."""
        build_info = self.read_metadata_file(self.BUILD_FILE)
        build_id = build_info['id']

        # Dir of all unpacked content to search for RPM files
        unpacked_content_path = os.path.join(self.input_dir, self.UNPACKED_ARCHIVES_DIR)

        for archive_type in os.listdir(unpacked_content_path):  # 'rpm', 'container_layer', 'maven'
            for archive in os.listdir(os.path.join(unpacked_content_path, archive_type)):
                path_to_archive = os.path.join(unpacked_content_path, archive_type, archive)
                # Assume that the artifact being analyzed was created by the main analyzer
                original_artifact = content.Artifact.nodes.get(filename=archive)

                for extension in self.FILE_EXTENSIONS:
                    search_path = os.path.join(path_to_archive, '**/*.' + extension)
                    for loose_artifact_batch in self.batches(glob.iglob(search_path,
                                                                        recursive=True)):
                        self.koji_session.multicall = True
                        for loose_artifact in loose_artifact_batch:
                            if not loose_artifact:
                                # can be None if it's the last batch
                                continue
                            # queue up the koji calls
                            if loose_artifact.endswith('.rpm'):
                                rpm = os.path.basename(loose_artifact)
                                log.info(f'Looking up RPM in Koji: {loose_artifact}')
                                self.koji_session.getRPM(rpm)
                            else:
                                md5_checksum = self.checksum(loose_artifact, md5)
                                log.info(
                                    f'Looking up archive in Koji: {md5_checksum}, {loose_artifact}')
                                self.koji_session.listArchives(checksum=md5_checksum)

                        responses = self.koji_session.multiCall()
                        # Process the individual responses. Responses are returned in the same
                        # order the calls are added, so we can zip it up to pair back with the
                        # file path.
                        for loose_artifact, response in zip(loose_artifact_batch, responses):
                            is_rpm = loose_artifact.endswith('.rpm')
                            relative_filepath = os.path.relpath(loose_artifact, path_to_archive)
                            # If Koji could not find it or there was some other error, log it
                            # and continue. Response is either a dict if an error, or a list of
                            # one element if found.
                            if isinstance(response, dict):
                                log.error(f'Error received from Koji looking up {relative_filepath}'
                                          f' embedded in {archive} in build {build_id}. Koji error '
                                          f'{response["faultString"]}')
                                continue

                            artifact_info = response[0]
                            if not artifact_info:
                                log.info(f'Cannot find build for {relative_filepath} embedded in '
                                         f'{archive} in build {build_id}.')
                                continue

                            if not is_rpm:
                                # listArchives returns a list where getRPM returns a hash directly
                                artifact_info = artifact_info[0]

                            artifact_build_id = artifact_info.get('build_id')
                            if not artifact_build_id:
                                log.error(f'Empty build found in Koji for {relative_filepath} '
                                          f'embedded in {archive} in build {build_id}')
                                continue

                            log.info(f'Linking discovered embedded artifact {relative_filepath} '
                                     f'embedded in {archive} in build {build_id}')
                            artifact_build = content.Build.get_or_create({
                                'id_': artifact_build_id,
                                'type_': 'build' if is_rpm else artifact_info['btype'],
                            })[0]

                            if is_rpm:
                                artifact = self.create_or_update_rpm_artifact_from_rpm_info(
                                    artifact_info)
                            else:
                                artifact = self.create_or_update_archive_artifact_from_archive_info(
                                    artifact_info)

                            self.conditional_connect(artifact.build, artifact_build)
                            self.conditional_connect(original_artifact.embedded_artifacts, artifact)
                            self.claim_file(path_to_archive, relative_filepath)

    def batches(self, iterable):
        """Return batches of self.KOJI_BATCH_SIZE length items from iterable.

        :param iterable iterable: Anything that can be iterated.
        :return: A list of KOJI_BATCH_SIZE items, or fewer if iterable is exhausted.
        :rtype: list
        """
        # stackoverflow.com/questions/8290397/how-to-split-an-iterable-in-constant-size-chunks
        args = [iter(iterable)] * self.KOJI_BATCH_SIZE
        return list(zip_longest(fillvalue=None, *args))
