# SPDX-License-Identifier: GPL-3.0+

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

    __buildroot_to_artifact = {}

    def __map_buildroot_to_artifact(self, buildroot_id, artifact):
        """
        Store the mapping in self.__buildroot_to_artifact.

        :param str buildroot_id: The id of the buildroot in question, eg. '1'
        :param Artifact artifact: The artifact in question.
        """
        self.__buildroot_to_artifact.setdefault(buildroot_id, [])
        self.__buildroot_to_artifact[buildroot_id].append(artifact)

    def _read_and_save_buildroots(self):
        """Save and link the rpms used in the buildroot for each artifact."""
        buildroots_info = self.read_metadata_file(self.BUILDROOT_FILE)
        for buildroot_id, buildroot_info in buildroots_info.items():
            log.debug('Creating artifacts for buildroot %s', buildroot_id)
            for rpm_info in buildroot_info:
                rpm = self.get_or_create_rpm_artifact_from_rpm_info(rpm_info)
                if buildroot_id not in self.__buildroot_to_artifact:
                    continue
                for artifact in self.__buildroot_to_artifact[buildroot_id]:
                    artifact.buildroot_artifacts.connect(rpm)

    def _construct_and_save_component(self, build_type, build_info):
        """
        Read the build info and construct the Component.

        :param str build_type: The type of the build (eg 'build' or 'mave')
        :param dict build_info: A dictionary of information from brew / koji
        :return: A tuple of component and version
        :rtype: tuple(Component, str)
        """
        if build_type == 'build':  # rpm build
            cnamespace = 'redhat'
            cname = build_info['name']
            ctype = 'rpm'
            cversion = '%s-%s' % (build_info['version'], build_info['release'])
        elif build_type == 'maven':
            # What we really want is the contents of the "Maven groupId" etc fields.
            # However they don't seem to be included in the brew response?!
            # Instead let's parse it out with what is (as best as I can tell) the algorithm.
            cnamespace, cname = build_info['name'].split('-', 1)
            cversion = build_info['version'].replace('_', '-')
            ctype = 'java'
        elif build_type == 'buildContainer':
            cnamespace = 'docker-image'
            cname = build_info['name']
            cversion = '%s-%s' % (build_info['version'], build_info['release'])
            ctype = 'image'
        else:
            return None, None

        component = self.get_or_create_component(
            canonical_namespace=cnamespace,
            canonical_name=cname,
            canonical_type=ctype)
        return component, cversion

    def run(self):
        """Do the actual processing."""
        build_info = self.read_metadata_file(self.BUILD_FILE)
        task_info = self.read_metadata_file(self.TASK_FILE)

        build_type = None
        if task_info:
            build_type = task_info['method']

        # construct the component
        component, canonical_version = self._construct_and_save_component(build_type, build_info)

        # construct the SourceLocation
        source = build_info['source']
        sourceLocation = self.get_or_create_source_location(source, canonical_version)
        sourceLocation.component.connect(component)

        # construct the build object
        build = self.get_or_create_build(build_info['id'], build_type)
        build.source_location.connect(sourceLocation)

        # record the rpms associated with this build
        rpms_info = self.read_metadata_file(self.RPM_FILE)
        for rpm_info in rpms_info:
            buildroot_id = rpm_info['buildroot_id']
            rpm = self.get_or_create_rpm_artifact_from_rpm_info(rpm_info)
            rpm.build.connect(build)
            self.__map_buildroot_to_artifact(buildroot_id, rpm)

        # record the artifacts
        archives_info = self.read_metadata_file(self.ARCHIVE_FILE)
        images_rpm_info = self.read_metadata_file(self.IMAGE_RPM_FILE)
        for archive_info in archives_info:
            log.debug('Creating build artifact %s', archive_info['id'])
            aid = archive_info['id']
            checksum = archive_info['checksum']
            filename = archive_info['filename']
            buildroot_id = archive_info['buildroot_id']
            # find the nested arch information or set noarch
            arch = archive_info.get('extra', {}).get('image', {}).get('arch', 'noarch')

            archive = self.get_or_create_archive_artifact(
                aid, filename, arch, checksum)
            archive.build.connect(build)
            self.__map_buildroot_to_artifact(buildroot_id, archive)

            if aid in images_rpm_info:
                # It's an image and we know it contains some rpms. Save them.
                for rpm_info in images_rpm_info[aid]:
                    rpm = self.get_or_create_rpm_artifact_from_rpm_info(rpm_info)
                    archive.embedded_artifacts.connect(rpm)

        self._read_and_save_buildroots()


if __name__ == '__main__':
    MainAnalyzer.main()
