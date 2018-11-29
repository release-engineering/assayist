# SPDX-License-Identifier: GPL-3.0+

import glob
import os

from hashlib import md5

from assayist.common.models import content
from assayist.processor.base import Analyzer
from assayist.processor.logging import log


class LooseArtifactAnalyzer(Analyzer):
    """
    Analyze RPMs/jars/similar that are embedded in the build artifacts or sources.

    RPMs we have to treat differently from other artifact types because Koji treats them
    differently and there is no way to look up an rpm by checksum in the Koji api. So,
    for RPMs we will look them up by filename, which should be uniquely identifying across
    a single Koji instance (assuming someone hasn't renamed the file).

    The intention for other artifact types (jar, pom, etc) is that we will checksum them
    and then look them up in koji by checksum. You can accomplish the same thing with
    koji-build-finder, but for our use-case doing it outselves was just as easy and made
    dependency management and debugging a lot simpler.

    The question on what to do with artifacts found embedded in the source dir is a good one.
    The schema does not currently allow for embedding artifacts in a SourceLocation. Instead
    the most reasonable (and safe) thing is that is consistent with our existing schema /
    queries is to assume that artifacts found embedded in the source are in fact embedded
    in every one of the build archives.
    """

    FILE_EXTENSIONS = ['rpm', 'zip', 'tar', 'tar.gz', 'tar.bz2', 'tar.xz', 'rar', 'ear',
                       'jar', 'war', 'sar', 'kar', 'pom.xml', 'pom', 'war', 'jdocbook',
                       'jdocbook-style', 'plugin']
    KOJI_BATCH_SIZE = 10

    def run(self):
        """
        Start the loose RPM analyzer.

        :raises AnalysisFailure: if the analyzer completed with errors
        """
        build_info = self.read_metadata_file(self.BUILD_FILE)
        self.build_id = build_info['id']
        build_type = build_info['type']

        if build_type not in self.SUPPORTED_BUILD_TYPES:
            log.info(f'Skipping build {self.build_id} because the build type "{build_type}" '
                     f'is not supported')
            return

        self.batch = []

        # Examine the source for embedded artifacts.
        source_path = os.path.join(self.input_dir, self.SOURCE_DIR)
        source_embedded_artifacts = []
        for loose_artifact in self.files_to_examine(source_path):
            # If we find it locally don't bother asking Koji about it again.
            artifact = self.local_lookup(loose_artifact)
            if artifact:
                source_embedded_artifacts.append(artifact)
                continue

            for artifact in self.add_to_and_maybe_execute_batch(loose_artifact, source_path):
                source_embedded_artifacts.append(artifact)

        # Wrap up any in-progress batch before moving on to the archives.
        for artifact in self.execute_batch_and_return_artifacts():
            source_embedded_artifacts.append(artifact)

        # Now examine the build artifacts.
        for archive, path_to_archive in self.unpacked_archives():
            # Assume that the artifact being analyzed was created by the main analyzer
            original_artifact = content.Artifact.nodes.get(filename=archive)
            # Assume that every artifact found in the source is embedded in every built artifact.
            for source_artifact in source_embedded_artifacts:
                original_artifact.embedded_artifacts.connect(source_artifact)

            for loose_artifact in self.files_to_examine(path_to_archive):
                relative_filepath = os.path.relpath(loose_artifact, path_to_archive)

                try:
                    artifact = self.local_lookup(loose_artifact)
                except FileNotFoundError:
                    # There are two potential causes here, both with symlinks:
                    # 1) There is a symlink that points to a file in a different
                    #    layer of the container.
                    # 2) It was a symlink to something we already analyzed and
                    #    claimed.
                    #
                    # Either way I don't think we really care. If it's already
                    # claimed then we've already established the link to this
                    # artifact. If it's referenceing something on a different
                    # layer of the container then we'll find it when we analyse
                    # that build (and that's the layer that needs to be respun
                    # anyway, since that's what contains the actual thing).
                    # Let's just claim the file and move on.
                    log.warning(f'Skipping already-claimed symlink in {archive}: '
                                f'{relative_filepath}')
                    self.claim_file(path_to_archive, relative_filepath)
                    continue

                # If we find it locally don't bother asking Koji about it again.
                if artifact:
                    self.conditional_connect(original_artifact.embedded_artifacts, artifact)
                    self.claim_file(path_to_archive, relative_filepath)
                    continue

                # Add the file to the batch of things to process. If this happens to
                # trigger a batch execution, handle the resulting Artifacts.
                for artifact in self.add_to_and_maybe_execute_batch(loose_artifact,
                                                                    path_to_archive,
                                                                    claim=True):
                    self.conditional_connect(original_artifact.embedded_artifacts, artifact)

            # Wrap up any in-progress batch before moving on to the next archive.
            for artifact in self.execute_batch_and_return_artifacts(claim=True):
                self.conditional_connect(original_artifact.embedded_artifacts, artifact)

    def local_lookup(self, loose_artifact):
        """
        Lookup the given file locally to see if we already know about it.

        Uses sha256 checksum to make that determination.

        :param str loose_artifact: The full path to the file in question.
        :raises FileNotFoundError: if the file could not be found to checksum.
        :return: The Artifact that we discovered with a local lookup, or None.
        :rtype: Artifact or None
        """
        sha256_checksum = self.checksum(loose_artifact)
        try:
            checksum_node = content.Checksum.nodes.first(checksum=sha256_checksum)
        except content.Checksum.DoesNotExist:
            return None

        # According to the schema a checksum can be associated with multiple Artifacts, but
        # according to reality that doesn't make much sense. Just return the "first one".
        artifacts = checksum_node.artifacts.all()
        if artifacts:
            log.info(f'Artifact already in database: {loose_artifact}')
            return artifacts[0]
        else:
            return None

    def unpacked_archives(self):
        """
        Generate name and path to every unpacked archive.

        :return: All (archive_name, path_to_archive) tuples. The path includes archive_name.
        :rtype: Iterable
        """
        # Dir of all unpacked content
        unpacked_content_path = os.path.join(self.input_dir, self.UNPACKED_ARCHIVES_DIR)
        for archive_type in os.listdir(unpacked_content_path):  # 'rpm', 'container_layer', etc
            archive_dir = os.path.join(unpacked_content_path, archive_type)
            for archive in os.listdir(archive_dir):
                path_to_archive = os.path.join(archive_dir, archive)
                yield archive, path_to_archive

    def files_to_examine(self, path_to_archive):
        """
        Generate the files with extensions we care about.

        :param str path_to_archive: The absolute path to the archive we are currently examining.
        :return: All filepaths that we want to examine as potential embedded Artifacts.
        :rtype: Iterable
        """
        for extension in self.FILE_EXTENSIONS:
            search_path = os.path.join(path_to_archive, '**/*.' + extension)
            for loose_artifact in glob.iglob(search_path, recursive=True):
                if os.path.isfile(loose_artifact):
                    yield loose_artifact

    def add_to_and_maybe_execute_batch(self, loose_artifact, path_to_archive, claim=False):
        """
        Add the given file to the koji multicall batch.

        If the batch is full, execute it and return the resulting Artifacts. Else
        return empty list.

        :param str loose_artifact: The absolute path to the file in question.
        :param str path_to_archive: The absolute path to the archive we are currently exporing.
        :param bool claim: If we should claim the file if we discover an artifact.
                           Default False.
        :return: A list of Artifacts created, or empty list.
        :rtype: list
        """
        if not self.batch:
            # We're at the beginning of a new batch, initialize the koji multicall session
            self.koji_session.multicall = True

        relative_filepath = os.path.relpath(loose_artifact, path_to_archive)
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

        self.batch.append((path_to_archive, relative_filepath))
        if len(self.batch) >= self.KOJI_BATCH_SIZE:
            return self.execute_batch_and_return_artifacts(claim)

        return []

    def execute_batch_and_return_artifacts(self, claim=False):
        """
        Execute the stored Koji batch and return the Artifacts created.

        :param bool claim: If we should claim the file if we discover an artifact.
                           Default False.
        :return: A list of Artifacts created.
        :rtype: list
        """
        ret = []
        if not self.batch:
            return ret  # gracefully exit early if batch is empty
        responses = self.koji_session.multiCall()
        # Process the individual responses. Responses are returned in the same
        # order the calls are added, so we can zip it up to pair back with the
        # file path.
        for (path_to_archive, relative_filepath), response in zip(self.batch, responses):
            archive = os.path.basename(path_to_archive)
            is_rpm = relative_filepath.endswith('.rpm')
            # If Koji could not find it or there was some other error, log it
            # and continue. Response is either a dict if an error, or a list of
            # one element if found.
            if isinstance(response, dict):
                log.error(f'Error received from Koji looking up {relative_filepath}'
                          f' embedded in {archive} in build {self.build_id}. Koji error '
                          f'{response["faultString"]}')
                continue

            artifact_info = response[0]
            if not artifact_info:
                log.info(f'Cannot find build for {relative_filepath} embedded in '
                         f'{archive} in build {self.build_id}.')
                continue

            if not is_rpm:
                # listArchives returns a list where getRPM returns a hash directly
                artifact_info = artifact_info[0]

            artifact_build_id = artifact_info.get('build_id')
            if not artifact_build_id:
                log.error(f'Empty build found in Koji for {relative_filepath} '
                          f'embedded in {archive} in build {self.build_id}')
                continue

            log.info(f'Linking discovered embedded artifact {relative_filepath} '
                     f'embedded in {archive} in build {self.build_id}')
            artifact_build = content.Build.get_or_create({
                'id_': artifact_build_id,
                'type_': 'build' if is_rpm else artifact_info['btype'],  # TODO bug!
            })[0]

            if is_rpm:
                artifact = self.create_or_update_rpm_artifact_from_rpm_info(artifact_info)
            else:
                artifact = self.create_or_update_archive_artifact_from_archive_info(artifact_info)

            self.conditional_connect(artifact.build, artifact_build)
            ret.append(artifact)
            if claim:
                self.claim_file(path_to_archive, relative_filepath)

        # Clear the processed batch.
        self.batch = []
        return ret
