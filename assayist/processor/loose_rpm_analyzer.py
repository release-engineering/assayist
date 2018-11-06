# SPDX-License-Identifier: GPL-3.0+

import glob
import os

from assayist.common.models import content
from assayist.processor.base import Analyzer
from assayist.processor.logging import log


class LooseRpmAnalyzer(Analyzer):
    """Analyze RPMs embedded in the build artifacts."""

    def run(self):
        """Start the loose RPM analyzer."""
        build_info = self.read_metadata_file(self.BUILD_FILE)
        build_id = build_info['id']

        # Remember current directory
        orig_dir = os.getcwd()

        # Switch to dir of all unpacked content to search for RPM files
        unpacked_content_path = os.path.join(self.input_dir, self.UNPACKED_ARCHIVES_DIR)
        os.chdir(unpacked_content_path)

        for archive_type in os.listdir():  # 'rpm', 'container_layer', 'maven', etc.
            for archive in os.listdir(archive_type):  # dir name == archive filename
                search_path = os.path.join(archive_type, archive, '**/*.rpm')
                for loose_rpm in glob.iglob(search_path, recursive=True):

                    loose_rpm_build, loose_rpm_info = self._get_associated_build(loose_rpm)
                    if not loose_rpm_build:
                        log.error(f'Cannot find build for {loose_rpm} embedded in {archive} in '
                                  f'build {build_id}')

                    loose_artifact = self.create_or_update_rpm_artifact_from_rpm_info(
                        loose_rpm_info)

                    if not loose_artifact.build.is_connected(loose_rpm_build):
                        loose_artifact.build.connect(loose_rpm_build)

                    # Assume that the artifact being analyzed was created by the main analyzer.
                    archive_obj = content.Artifact.nodes.get(filename=archive)
                    self.conditional_connect(archive_obj.embedded_artifacts, loose_artifact)

                    # TODO: Claim loose RPM file once PR44 is merged
                    # path_to_archive = os.path.join(unpacked_content_path, archive_type, archive)
                    # archive_file = os.path.relpath(loose_rpm, path_to_archive)
                    # self.claim_file(path_to_archive, archive_file)

        # Return back to original directory
        os.chdir(orig_dir)

    def _get_associated_build(self, rpm):
        """Get the build that produced the specified RPM.

        :param rpm: RPM identified by a file name
        :return: new or existing Build associated with the specified RPM and the RPM info dict
        :rtype: tuple(Build, dict)
        """
        # Find related RPM in Koji by the file name, e.g. `python-django-1.8.11-1.el7ost.noarch.rpm`
        # The `.rpm` extension is stripped automatically by Koji.
        rpm_info = self.koji_session.getRPM(rpm)
        if not rpm_info:
            return None, None

        build_id = rpm_info.get('build_id')
        if not build_id:
            return None, None

        build = content.Build.get_or_create({
            'id_': build_id,
            'type_': 'rpm',
        })[0]

        return build, rpm_info
