# SPDX-License-Identifier: GPL-3.0+

from assayist.processor.base import Analyzer
from assayist.processor.logging import log


class MainAnalyzer(Analyzer):
    """
    Look at the json brew output and write neomodels for the basic items identified:
     * The Component
     * The direct SourceLocation
     * The Build itself
     * Any produced Artifacts (RPMs or otherwise)
     * Any RPMs used in the buildroot
     * If it's an image build, an RPMs included in the image
    """
    buildroot_to_artifact = {}

    def map_buildroot_to_artifact(self, buildroot_id, artifact_id):
        """ Store the mapping in self.buildroot_to_artifact """
        if buildroot_id in self.buildroot_to_artifact:
            self.buildroot_to_artifact[buildroot_id].append(artifact_id)
        else:
            self.buildroot_to_artifact[buildroot_id] = [artifact_id]

    def read_and_save_buildroots(self):
        """ Save and link the rpms used in the buildroot for each artifact. """
        buildroots_info = self.read_metadata_file(self.BUILDROOT_FILE)
        for buildroot_id in buildroots_info:
            log.debug("Creating artifacts for buildroot %s", buildroot_id)
            for rpm_info in buildroots_info[buildroot_id]:
                rpm = self.get_or_create_rpm_artifact_from_hash(rpm_info)
                if buildroot_id in self.buildroot_to_artifact:
                    for artifact in self.buildroot_to_artifact[buildroot_id]:
                        artifact.buildroot_artifacts.connect(rpm)

    def construct_and_save_component(self, build_type, build_info):
        """
        Read the build info and contruct the Component.
        Returns: (Component, canonical_version)
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

        self.get_or_create_component(
            canonical_namespace=cnamespace,
            canonical_name=cname,
            canonical_type=ctype)
        return component, cversion

    def run(self):
        """ Do the actual processing. """
        build_info = self.read_metadata_file(self.BUILD_FILE)
        task_info = self.read_metadata_file(self.TASK_FILE)

        build_type = None
        if task_info:
            build_type = task_info['method']

        # construct the component
        component, canonical_version = self.construct_and_save_component(build_type, build_info)

        # construct the SourceLocation
        source = build_info['source']
        sourceLocation = self.get_or_create_source_location(source, canonical_version)
        sourceLocation.component.connect(component)

        # construct the build object
        build = self.get_or_create_build(build_info['id'], build_type)
        build.source.connect(sourceLocation)

        # if it's an rpm build look at the rpm output and create artifacts
        if build_type == 'build':
            rpms_info = self.read_metadata_file(self.RPM_FILE)
            for rpm_info in rpms_info:
                buildroot_id = rpm_info['buildroot_id']
                rpm = self.get_or_create_rpm_artifact_from_hash(rpm_info)
                rpm.build.connect(build)
                self.map_buildroot_to_artifact(buildroot_id, rpm)
                self.read_and_save_buildroots()
                return  # finished processing, rpm builds don't have anything else

        # else not an rpm build, record the artifacts
        archives_info = self.read_metadata_file(self.ARCHIVE_FILE)
        images_rpm_info = self.read_metadata_file(self.IMAGE_RPM_FILE)
        for archive_info in archives_info:
            log.debug("Creating build artifact %s", buildroot_id)
            aid = archive_info['id']
            checksum = archive_info['checksum']
            filename = archive_info['filename']
            buildroot_id = archive_info['buildroot_id']
            arch = 'noarch'
            if 'extra' in archive_info \
                    and 'image' in archive_info['extra'] \
                    and 'arch' in archive_info['extra']['image']:
                arch = archive_info['extra']['image']['arch']

            archive = self.get_or_create_archive_artifact(
                aid, filename, arch, checksum)
            archive.build.connect(build)
            self.map_buildroot_to_artifact(buildroot_id, archive)

            if aid in images_rpm_info:
                # It's an image and we know it contains some rpms. Save them.
                for rpm_info in images_rpm_info[aid]:
                    rpm = self.get_or_create_rpm_artifact_from_hash(rpm_info)
                    archive.embedded_artifacts.connect(rpm)


if __name__ == "__main__":
    MainAnalyzer.main()
