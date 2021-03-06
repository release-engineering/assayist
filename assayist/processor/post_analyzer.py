# SPDX-License-Identifier: GPL-3.0+

import os

from assayist.common.models import content
from assayist.processor.base import Analyzer
from assayist.processor.logging import log


# List of directories to ignore when searching for unknown files.
# Do not include the leading root dir because the analyzer works with paths relative to the
# unpacked content. Must be a tuple.
IGNORED_DIRS = (
    'var/lib/yum/',  # Yum ghost files
    'var/log/',  # Log files
    'var/cache/',  # Cache files
    'var/spool/',  # Spool data
)


class PostAnalyzer(Analyzer):
    """Performs post-analysis."""

    def run(self):
        """
        Start the post analyzer.

        :raises AnalysisFailure: if the analyzer completed with errors
        """
        build_info = self.read_metadata_file(self.BUILD_FILE)
        build_id = build_info['id']

        if build_info['type'] != self.CONTAINER_BUILD_TYPE:
            # Post analysis consists of recording unknown files, which only makes sense for
            # container builds. RPM or maven builds will not include any unindentified files.
            log.info(f'Skipping build {build_id} because the build is not a container')
            return

        # Dir of all unpacked container content
        unpacked_container_layer = os.path.join(self.input_dir, self.UNPACKED_CONTAINER_LAYER_DIR)

        for archive in os.listdir(unpacked_container_layer):
            path_to_archive = os.path.join(unpacked_container_layer, archive)
            # Assume that the artifact being analyzed was created by the main analyzer.
            archive_obj = content.Artifact.nodes.get(filename=archive)

            for unknown_file in self.walk(path_to_archive):
                path, filename = os.path.split(os.path.relpath(unknown_file, path_to_archive))

                if path.startswith(IGNORED_DIRS):
                    continue

                log.info(f'Found unknown file in {archive}: /{path}/{filename}')
                unknown_file = content.UnknownFile.get_or_create({
                    'checksum': self.checksum(unknown_file),
                    'filename': filename,
                    'path': '/' + path,  # Add leading root dir
                })[0]
                self.conditional_connect(archive_obj.unknown_files, unknown_file)
