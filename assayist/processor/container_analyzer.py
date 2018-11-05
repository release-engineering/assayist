# SPDX-License-Identifier: GPL-3.0+

from assayist.common.models import content
from assayist.processor.base import Analyzer
from assayist.processor.logging import log


class ContainerAnalyzer(Analyzer):
    """Analyzes the parent builds of a specific build."""

    def run(self):
        """Start the container analyzer."""
        build_info = self.read_metadata_file(self.BUILD_FILE)
        build_id = build_info['id']

        if not self.is_container_build(build_info):
            log.info(f'Skipping build {build_id} because the build is not a container')
            return

        # If this build has no parent image build, there is nothing to do here.
        parent_build_id = build_info['extra']['image'].get('parent_build_id')
        if parent_build_id is None:
            return

        # This container's build is assumed to exist since it is created by the main analyzer.
        build = content.Build.nodes.get(id_=build_id)

        # Process parent build and embed all artifacts of the parent build to the artifacts of
        # this build's artifacts.
        arch_to_artifact = self._create_or_update_parent(parent_build_id)

        for archive in build.artifacts.filter(type_='container').all():
            related_archive = arch_to_artifact.get(archive.architecture)
            if not related_archive:
                log.error('no artifact to link to, architecture does not exist in parent build')
                continue

            archive.embedded_artifacts.connect(related_archive)

        # Process parent builds used as buildroots (those specified in `parent_image_builds`
        # besides the `parent_build_id`. Embed all artifacts of each parent build as buildroot
        # artifacts of this build's artifacts.
        parent_image_builds = build_info['extra']['image']['parent_image_builds'].values()
        parent_image_builds_ids = {build['id'] for build in parent_image_builds
                                   if build['id'] != parent_build_id}

        for buildroot_parent_build_id in parent_image_builds_ids:
            arch_to_artifact = self._create_or_update_parent(buildroot_parent_build_id)

            for archive in build.artifacts.filter(type_='container').all():
                related_archive = arch_to_artifact.get(archive.architecture)
                if not related_archive:
                    log.error('no artifact to link to, architecture does not exist in parent build')
                    continue

                archive.buildroot_artifacts.connect(related_archive)

    def _create_or_update_parent(self, build_id):
        """Create or update a parent build and its archives (container images).

        :param build_id: build ID of the parent build to process
        :return: dictionary of container image artifacts indexed by architectures
        :rtype: dict
        """
        parent_build = content.Build.get_or_create({
            'id_': build_id,
            'type_': 'buildContainer',
        })[0]

        archives = self.koji_session.listArchives(build_id)
        arch_to_artifact = {}
        not_container_msg = 'Skipping archive {0} since it\'s not a container image'

        for archive in archives:
            if archive['btype'] != 'image':
                log.debug(not_container_msg.format(archive['id']))
                continue

            architecture = archive['extra']['image']['arch']
            if architecture in arch_to_artifact:
                log.error(f'Build {build_id} has more than one container image with the arch '
                          f'{architecture}')
                continue

            # Create or get the archive artifact that is the product of this build
            artifact = self.create_or_update_archive_artifact_from_archive_info(archive)
            arch_to_artifact[artifact.architecture] = artifact

            # If an archive was created in the previous step, connect it to this build.
            if not artifact.build.is_connected(parent_build):
                artifact.build.connect(parent_build)

        return arch_to_artifact
