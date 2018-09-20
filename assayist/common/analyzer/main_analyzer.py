# SPDX-License-Identifier: GPL-3.0+

from .base import Analyzer
from ..models import content, source

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


    def construct_rpm_artifact(self, rpm_info):
        """ parse the dict and build and return an rpm artifact """
        aid = rpm_info['id']
        buildroot_id = rpm_info['buildroot_id']
        checksum = rpm_info['payloadhash']
        name = rpm_info['name']
        # If epoch is None treat it as 0 instead
        epoch = rpm_info['epoch'] if rpm_info['epoch'] else "0"
        version = rpm_info['version']
        release = rpm_info['release']
        arch = rpm_info['arch']
        nevra = "%s-%s:%s-%s.%s" % (name, epoch, version, release, arch)

        # Actually NEVRA for RPMs even though actual filenames never include Epoch
        rpm = content.Artifact(
                architecture=arch,
                archive_id=aid,
                checksum=checksum,
                filename=nevra).save()
        return rpm


    def read_and_save_buildroots(self):
        """ Save and link the rpms used in the buildroot for each artifact. """
        buildroots_info = self.read_metadata_file(self.BUILDROOT_FILE)
        for buildroot_id in buildroots_info:
            for rpm_info in buildroots_info[buildroot_id]:
                rpm = self.construct_rpm_artifact(rpm_info)
                for artifact in self.buildroot_to_artifact[buildroot_id]:
                    artifact.buildroot_artifacts.connect(rpm)


    def construct_and_save_component(self, build_type, build_info):
        """
        Read the build info and contruct the Component.
        Returns: (Component, canonical_version)
        """
        if build_type == 'build': # rpm build
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

        component = source.Component(
                canonical_namespace=cnamespace,
                canonical_name=cname,
                canonical_type=ctype).save()
        return component, cversion


    def run(self):
        """ Do the actual processing. """
        build_info = self.read_metadata_file(self.BUILD_FILE)
        task_info = self.read_metadata_file(self.TASK_FILE)

        build_type = None
        if task_info:
            build_type = task_info['method']

        # construct the component
        component, canonical_version = construct_and_save_component(build_type, build_info)

        # construct the SourceLocation
        source = build_info['source']
        sourceLocation = source.SourceLocation(url=source,
                canonical_version=canonical_version).save()
        sourceLocation.component.connect(component)

        # construct the build object
        build = content.Build(id_=build_info['id'], type=build_type).save()
        build.source.connect(sourceLocation)

        # if it's an rpm build look at the rpm output and create artifacts
        if build_type == 'build':
            rpms_info = self.read_metadata_file(self.RPM_FILE)
            for rpm_info in rpms_info:
                buildroot_id = rpm_info['buildroot_id']
                rpm = self.construct_rpm_artifact(rpm_info)
                rpm.build.connect(build)
                self.map_buildroot_to_artifact(buildroot_id, rpm)
                self.read_and_save_buildroots()
                return # finished processing, rpm builds don't have anything else

        # else not an rpm build, record the artifacts
        archives_info = self.read_metadata_file(self.ARCHIVE_FILE)
        images_rpm_info = self.read_metadata_file(self.IMAGE_RPM_FILE)
        for archive_info in archives_info:
            aid = archive_info['id']
            checksum = archive_info['checksum']
            filename = archive_info['filename']
            buildroot_id = archive_info['buildroot_id']
            arch = 'noarch'
            if 'extra' in archive_info \
                    and 'image' in archive_info['extra'] \
                    and 'arch' in archive_info['extra']['image']:
                arch = archive_info['extra']['image']['arch']

            archive = content.Artifact(
                    architecture=arch,
                    archive_id=aid,
                    checksum=checksum,
                    filename=filename)
            archive.build.connect(build)
            self.map_buildroot_to_artifact(buildroot_id, archive)

            if aid in images_rpm_info:
                # It's an image and we know it contains some rpms. Save them.
                for rpm_info in images_rpm_info[aid]:
                    rpm = self.construct_rpm_artifact(rpm_info)
                    archive.embedded_artifacts.connect(rpm)


if __name__ == "__main__":
    MainAnalyzer.main()
