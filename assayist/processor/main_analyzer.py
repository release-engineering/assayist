# SPDX-License-Identifier: GPL-3.0+

from assayist.common.models import content, source
from assayist.processor.base import Analyzer
from assayist.processor.logging import log


class MainAnalyzer(Analyzer):
    """
    Look at the json brew output and add basic information to the database.

    This analyzer is responsible for adding the following:
     * The Component
     * The direct SourceLocation
     * The Build itself
     * Any produced Artifacts (RPMs or otherwise)
     * Any RPMs used in the buildroot
     * If it's an image build, an RPMs included in the image
    """

    _buildroot_to_artifact = {}

    def _map_buildroot_to_artifact(self, buildroot_id, artifact):
        """
        Store the mapping in self._buildroot_to_artifact.

        :param str buildroot_id: The id of the buildroot in question, eg. '1'
        :param Artifact artifact: The artifact in question.
        """
        self._buildroot_to_artifact.setdefault(buildroot_id, [])
        self._buildroot_to_artifact[buildroot_id].append(artifact)

    def _read_and_save_buildroots(self):
        """Save and link the rpms used in the buildroot for each artifact."""
        buildroots_info = self.read_metadata_file(self.BUILDROOT_FILE)
        for buildroot_id, buildroot_info in buildroots_info.items():
            log.debug('Creating artifacts for buildroot %s', buildroot_id)
            for rpm_info in buildroot_info:
                rpm = self.create_or_update_rpm_artifact_from_rpm_info(rpm_info)
                if buildroot_id not in self._buildroot_to_artifact:
                    continue
                for artifact in self._buildroot_to_artifact[buildroot_id]:
                    artifact.buildroot_artifacts.connect(rpm)

    def _construct_and_save_component(self, build_type, build_info):
        """
        Read the build info and construct the Component.

        :param str build_type: The type of the build (eg 'build' or 'maven')
        :param dict build_info: A dictionary of information from brew / koji
        :return: A tuple of component and version
        :rtype: tuple(Component, str)
        """
        if build_type == 'build':  # rpm build
            cnamespace = 'redhat'
            cname = build_info['name']
            ctype = 'rpm'
            epoch = '0'
            if 'epoch' in build_info and build_info['epoch']:
                epoch = build_info['epoch']
            cversion = '%s-%s-%s' % (epoch, build_info['version'], build_info['release'])
        elif build_type == 'maven':
            # If it's a maven build then the maven info file should exist with the info we need.
            maven_info = self.read_metadata_file(self.MAVEN_FILE)
            cnamespace = maven_info['group_id']
            cname = maven_info['artifact_id']
            cversion = maven_info['version']
            ctype = 'java'
        elif build_type == 'buildContainer':
            # Theoretically this should exist for buildContainer builds.
            # Get the repo / commit identifier and use it to extract namespace and name.
            pulls = build_info.get('extra', {}).get('image', {}).get('index', {}).get('pull', [])
            best_pull_list = [x for x in pulls if '@' in x]
            if best_pull_list:
                best_pull = best_pull_list[0]
                cnamespace, rest = best_pull.split('/', 1)
                cname, _ = rest.split('@', 1)
            else:
                cnamespace = 'docker'
                cname = build_info['name']
            cversion = '%s-%s' % (build_info['version'], build_info['release'])
            ctype = 'docker'
        else:
            return None, None

        component = source.Component.get_or_create({
            'canonical_namespace': cnamespace,
            'canonical_name': cname,
            'canonical_type': ctype})[0]
        return component, cversion

    def run(self):
        """Do the actual processing."""
        build_info = self.read_metadata_file(self.BUILD_FILE)
        task_info = self.read_metadata_file(self.TASK_FILE)

        build_type = None
        if task_info:
            build_type = task_info['method']
        elif self.is_container_build(build_info):
            build_type = 'buildContainer'

        # construct the component
        component, canonical_version = self._construct_and_save_component(build_type, build_info)

        # construct the local SourceLocation
        source = build_info['source']
        local_source_location = self.create_or_update_source_location(
            source, component, canonical_version)

        # construct the build object
        build = content.Build.get_or_create({
            'id_': build_info['id'],
            'type_': build_type})[0]
        build.source_location.connect(local_source_location)

        # record the rpms associated with this build
        rpms_info = self.read_metadata_file(self.RPM_FILE)
        for rpm_info in rpms_info:
            buildroot_id = rpm_info['buildroot_id']
            rpm = self.create_or_update_rpm_artifact_from_rpm_info(rpm_info)
            rpm.build.connect(build)
            self._map_buildroot_to_artifact(buildroot_id, rpm)

        # record the artifacts
        archives_info = self.read_metadata_file(self.ARCHIVE_FILE)
        for archive_info in archives_info:
            if archive_info['btype'] == 'log':
                # No one cares about logs
                continue

            log.debug('Creating build artifact %s', archive_info['id'])
            archive = self.create_or_update_archive_artifact_from_archive_info(archive_info)
            archive.build.connect(build)
            self._map_buildroot_to_artifact(archive_info['buildroot_id'], archive)

        self._read_and_save_buildroots()
