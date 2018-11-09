# SPDX-License-Identifier: GPL-3.0+

from itertools import chain

from assayist.common.models import content
from assayist.processor.base import Analyzer
from assayist.processor.logging import log


class ContainerRPMAnalyzer(Analyzer):
    """Analyze the RPMs in a container image layer."""

    def run(self):
        """Start the container RPM analyzer."""
        build_info = self.read_metadata_file(self.BUILD_FILE)
        build_id = build_info['id']
        if not self.is_container_build(build_info):
            log.info(f'Skipping build {build_id} because the build is not a container')
            return

        # Create a mapping of arch to archive (container image) so we can easily map to the
        # parent container archives in a future loop
        arch_to_archive = {}
        not_container_msg = 'Skipping archive {0} since it\'s not a container image'
        for archive in self.read_metadata_file(self.ARCHIVE_FILE):
            if not self.is_container_archive(archive):
                log.debug(not_container_msg.format(archive['id']))
                continue
            arch = archive['extra']['image']['arch']
            if arch in arch_to_archive:
                log.error(
                    f'Build {build_id} has more than one container image with the arch {arch}')
                continue
            arch_to_archive[arch] = archive

        parent_build_id = build_info['extra']['image'].get('parent_build_id')
        # If there is a parent to this image, then only get the RPMs installed in this layer
        # and mark them as embedded artifacts on this container image
        if parent_build_id is not None:
            # Find the RPMs installed in this layer versus the parent image
            for archive in self.koji_session.listArchives(parent_build_id):
                if not self.is_container_archive(archive):
                    log.debug(not_container_msg.format(archive['id']))
                    continue
                arch = archive['extra']['image']['arch']
                if arch not in arch_to_archive:
                    log.debug(
                        f'The parent build {parent_build_id} contains an extra arch of {arch}')
                    continue

                rpms = self._get_rpms_diff(archive['id'], arch_to_archive[arch]['id'])
                self._process_embedded_rpms(arch_to_archive[arch], rpms)
        # If there is no parent, then this is a base image. Just get all the RPMs installed in
        # the image and mark them as embedded artifacts in this container image.
        else:
            image_rpm_file = self.read_metadata_file(self.IMAGE_RPM_FILE)
            for archive in arch_to_archive.values():
                rpms = image_rpm_file.get(archive['id'])
                self._process_embedded_rpms(archive, rpms)

    def _process_embedded_rpms(self, container_archive, rpms):
        """
        Add the nodes and relationships in Neo4j and claim the files these RPMs install.

        :param dict container_archive: the Koji archive of the container these RPMs are embedded in
        :param list rpms: the list of RPMs that are embedded in the container
        """
        artifact_obj = content.Artifact.get_or_create({
            'archive_id': container_archive['id'],
            'type_': 'container',
        })[0]

        # Dictionary to cache Neo4j Build objects
        build_id_to_obj = {}

        self.koji_session.multicall = True
        for rpm in rpms:
            rpm_artifact_obj = self.create_or_update_rpm_artifact_from_rpm_info(rpm)
            artifact_obj.embedded_artifacts.connect(rpm_artifact_obj)

            if rpm['build_id'] not in build_id_to_obj:
                build_id_to_obj[rpm['build_id']] = content.Build.get_or_create({
                    'id_': rpm['build_id'], 'type_': 'rpm'})[0]
            build_id_to_obj[rpm['build_id']].artifacts.connect(rpm_artifact_obj)

            self.koji_session.listRPMFiles(rpm['id'])

        # Query for list of all files in all RPMs in one call.
        rpm_files = self.koji_session.multiCall()

        # Claim the files these RPMs installed in the container image layer
        for file_ in chain.from_iterable(chain.from_iterable(rpm_files)):
            file_path = file_['name']
            self.claim_container_file(container_archive, file_path)

    def _get_rpms_diff(self, parent_archive_id, child_archive_id):
        """
        Determine the RPMs installed in the "child" container image layer.

        :param int parent_archive_id: the archive ID of the parent container image layer
        :param int child_archive_id: the archive ID of the child container image layer
        :return: a list of the RPMs (Koji RPM info dictionaries) installed in the child container
            image layer
        :rtype: list
        """
        parent_rpm_ids = set()
        for rpm in self.koji_session.listRPMs(imageID=parent_archive_id):
            parent_rpm_ids.add(rpm['id'])

        child_rpm_ids = set()
        id_to_rpm = {}
        for rpm in self.koji_session.listRPMs(imageID=child_archive_id):
            id_to_rpm[rpm['id']] = rpm
            child_rpm_ids.add(rpm['id'])

        diff_rpms = []
        for rpm_id in (child_rpm_ids - parent_rpm_ids):
            diff_rpms.append(id_to_rpm[rpm_id])
        return diff_rpms

    @staticmethod
    def is_container_archive(archive):
        """
        Inspect the archive to see if its a container archive.

        :param dict archive: the Koji archive to inspect
        :return: a boolean determining if it's a container archive
        :rtype: bool
        """
        if archive['btype'] != 'image':
            return False

        try:
            archive['extra']['image']['arch']
            return True
        # If archive['extra'] is None, then a TypeError is raised. If one of the keys is missing,
        # then a KeyError is raised.
        except (TypeError, KeyError):
            return False
