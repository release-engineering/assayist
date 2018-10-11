# SPDX-License-Identifier: GPL-3.0+

from abc import ABC, abstractmethod
import json
import os

import neomodel

from assayist.common.models import content, source
from assayist.processor.configuration import config
from assayist.processor.logging import log


class Analyzer(ABC):
    """Base Abstract class that analyzers will inherit from."""

    METADATA_DIR = '/metadata'
    BUILD_FILE = 'buildinfo.json'
    TASK_FILE = 'taskinfo.json'
    MAVEN_FILE = 'maveninfo.json'
    RPM_FILE = 'rpms.json'
    ARCHIVE_FILE = 'archives.json'
    IMAGE_RPM_FILE = 'image-rpms.json'
    BUILDROOT_FILE = 'buildroot-components.json'

    def main(self):
        """Call this to run the analyzer."""
        neomodel.db.set_connection(config.DATABASE_URL)
        # run the analyzer in a transaction
        neomodel.db.begin()
        try:
            self.run()
            log.debug('Analyzer completed successfully, committing.')
            neomodel.db.commit()
        except Exception as e:
            log.exception('Error encountered executing Analyzer, rolling back transaction.')
            neomodel.db.rollback()
            raise

    @abstractmethod
    def run(self):
        """Implement analyzer code here in your subclass."""

    def read_metadata_file(self, in_file, in_dir=METADATA_DIR):
        """
        Read and return the specified json metadata file or an empty dict.

        :param str in_file: The name of the input file to read. Probably one of the class constants.
        :param str in_dir: The directory the file is in. Defaults to METADATA_DIR.
        :return: a dict or list read from the file, or an empty dict
        :rtype: {}
        :raises ValueError: if the file was not valid json content
        """
        filename = os.path.join(in_dir, in_file)
        if os.path.isfile(filename):
            with open(filename, 'r') as f:
                return json.load(f)
        else:
            log.debug('File not found: %s, returning empty dict', filename)
            return {}

    def __create_or_update_artifact(self, archive_id, archive_type, arch, filename, checksum):
        artifact = content.Artifact.create_or_update({
            'archive_id': archive_id,
            'type_': archive_type,
            'architecture': arch,
            'filename': filename})[0]

        checksum_node = content.Checksum.create_or_update({
            'checksum': checksum,
            'algorithm': content.Checksum.guess_type(checksum),
            'checksum_source': 'unsigned'})[0]

        artifact.checksums.connect(checksum_node)
        return artifact

    def create_or_update_rpm_artifact(self, rpm_id, name, version, release, arch, checksum):
        """
        Create or update an Artifact for this rpm.

        :param str rpm_id: the rpm's id
        :param str name: the rpm's name, eg 'kernel'
        :param str version: the rpm's version, eg '1'
        :param str release: the rpm's release, eg '2.el7'
        :param str arch: the rpm's arch, eg 'x86_64'
        :param str checksum: the rpm's checksum, eg 'deadbeef1234'
        :return: an Artifact object
        :rtype: assayist.common.models.content.Artifact
        """
        # RPM lists from Brew don't contain filename, but that's okay because they follow a
        # strict pattern.
        filename = f'{name}-{version}-{release}.{arch}.rpm'
        if arch == 'src':
            _type = 'srpm'
        else:
            _type = 'rpm'
        return self.__create_or_update_artifact(rpm_id, _type, arch, filename, checksum)

    def create_or_update_rpm_artifact_from_rpm_info(self, rpm_info):
        """
        Create or update an Artifact for this rpm from a dictionary.

        :param dict rpm_info: A dictionary of information, like one that comes from brew.
                             Must contain the fields used in create_or_update_rpm_artifact.
        :return: an Artifact object
        :rtype: assayist.common.models.content.Artifact
        """
        return self.create_or_update_rpm_artifact(
            rpm_id=rpm_info['id'],
            name=rpm_info['name'],
            version=rpm_info['version'],
            release=rpm_info['release'],
            arch=rpm_info['arch'],
            checksum=rpm_info['payloadhash'])

    def create_or_update_archive_artifact(self, archive_id, filename, arch, archive_type, checksum):
        """
        Create or update an Artifact for this archive.

        :param str archive_id: the archives's id
        :param str filename: the archive's filename, eg 'maven.jar'
        :param str arch: the archive's architecture, eg 'x86_64' or None
        :param str archive_type: the archive's type, eg 'maven'
        :param str checksum: the archive's checksum, eg 'deadbeef1234'
        :return: an Artifact object
        :rtype: assayist.common.models.content.Artifact
        """
        if archive_type == 'image':
            _type = 'container'
        elif archive_type == 'maven':
            _type = 'maven'
        else:
            _type = 'other'
        return self.__create_or_update_artifact(archive_id, _type, arch, filename, checksum)

    def create_or_update_source_location(self, url, canonical_version):
        """
        Create or update SourceLocation.

        :param str url: the url and possibly commit hash of the source location
        :param str canonical_version: (optional) the version of the component that
                                      corresponds with this commit id
        :return: a SourceLocation object
        :rtype: assayist.common.models.source.SourceLocation
        """
        sl = source.SourceLocation.create_or_update({'url': url})[0]
        if canonical_version:
            sl.canonical_version = canonical_version
        return sl.save()
