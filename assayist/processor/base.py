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

    METADATA_DIR = '/metadata/'
    MESSAGE_FILE = METADATA_DIR + 'message.json'
    BUILD_FILE = METADATA_DIR + 'buildinfo.json'
    TASK_FILE = METADATA_DIR + 'taskinfo.json'
    RPM_FILE = METADATA_DIR + 'rpms.json'
    ARCHIVE_FILE = METADATA_DIR + 'archives.json'
    IMAGE_RPM_FILE = METADATA_DIR + 'image-rpms.json'
    BUILDROOT_FILE = METADATA_DIR + 'buildroot-components.json'

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

    def read_metadata_file(self, in_file):
        """
        Read and return the specified json metadata file or an empty dict.

        :param str in_file: The path to the input file to read. Probably one of the class constants.
        :return: a dict or list read from the file, or an empty dict
        :rtype: {}
        :raises ValueError: if the file was not valid json content
        """
        if os.path.isfile(in_file):
            with open(in_file, 'r') as f:
                return json.load(f)
        else:
            log.debug('File not found: %s, returning empty dict', in_file)
            return {}

    def get_or_create_build(self, build_id, build_type):
        """
        Get or create a build object.

        :param str build_id: the id of the build
        :param str build_type: the type of the build (eg. "build", "maven", "buildContainer")
        :return: a Build object
        :rtype: assayist.common.models.content.Build
        """
        return content.Build.get_or_create({
            'id_': build_id,
            'type': build_type})[0]

    def get_or_create_rpm_artifact(self, id, name, version, release, arch, checksum):
        """
        Create or update an Artifact for this rpm.

        :param str id: the rpm's id
        :param str name: the rpm's name, eg 'kernel'
        :param str version: the rpm's version, eg '1'
        :param str release: the rpm's release, eg '2.el7'
        :param str arch: the rpm's arch, eg 'x86_64'
        :param str checksum: the rpm's checksum, eg 'deadbeef1234'
        :return: an Artifact object
        :rtype: assayist.common.models.content.Artifact
        """
        filename = f'{name}-{version}-{release}.{arch}.rpm'
        return content.Artifact.create_or_update({
            'rpm_id': id,
            'archive_id': '0',
            'architecture': arch,
            'checksum': checksum,
            'filename': filename})[0]

    def get_or_create_rpm_artifact_from_rpm_info(self, rpm_info):
        """
        Create or update an Artifact for this rpm from a dictionary.

        :param str rpm_info: A dictionary of information, like one that comes from brew.
                             Must contain the fields used in get_or_create_rpm_artifact.
        :return: an Artifact object
        :rtype: assayist.common.models.content.Artifact
        """
        return self.get_or_create_rpm_artifact(
            id=rpm_info['id'],
            name=rpm_info['name'],
            version=rpm_info['version'],
            release=rpm_info['release'],
            arch=rpm_info['arch'],
            checksum=rpm_info['payloadhash'])

    def get_or_create_archive_artifact(self, archive_id, filename, arch, checksum):
        """
        Create or update an Artifact for this archive.

        :param str archive_id: the archives's id
        :param str filename: the archive's filename, eg 'maven.jar'
        :param str arch: the archive's architecture, eg 'x86_64' or None
        :param str checksum: the archive's checksum, eg 'deadbeef1234'
        :return: an Artifact object
        :rtype: assayist.common.models.content.Artifact
        """
        return content.Artifact.create_or_update({
            'archive_id': archive_id,
            'rpm_id': '0',
            'architecture': arch,
            'checksum': checksum,
            'filename': filename})[0]

    def get_or_create_source_location(self, url, canonical_version):
        """
        Create or update SourceLocation.

        :param str url: the url and possibly commit hash of the source location
        :param str canonical_version: (optional) the version of the componenet that
                                      corresponds with this commit id
        :return: a SourceLocation object
        :rtype: assayist.common.models.source.SourceLocation
        """
        sl = source.SourceLocation.get_or_create({'url': url})[0]
        if canonical_version:
            sl.canonical_version = canonical_version
        return sl

    def get_or_create_component(self, canonical_namespace, canonical_name, canonical_type):
        """
        Create or update Componenet

        :param str canonical_namespace: the namespace of the componenet, eg. 'com.redhat'
        :param str canonical_name: the name of the componenet, eg. 'maven'
        :param str canonical_type: the type of the componenet, eg. 'java'
        :return: a Component object
        :rtype: assayist.common.models.source.Component
        """
        return source.Component.get_or_create({
            'canonical_namespace': canonical_namespace,
            'canonical_name': canonical_name,
            'canonical_type': canonical_type})[0]
