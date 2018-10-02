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
        """Read and return the specified json metadata file or an empty dict."""
        if os.path.isfile(in_file):
            with open(in_file, 'r') as f:
                return json.load(f)
        else:
            log.debug('File not found: %s, returning empty dict', in_file)
            return {}

    def get_or_create_build(self, build_id, build_type):
        """Get or create a build object."""
        return content.Build.get_or_create({
            'id_': build_id,
            'type': build_type})[0]

    def get_or_create_rpm_artifact(self, id, name, version, release, arch, checksum):
        """Fetch or create an Artifact for this rpm."""
        filename = f'{name}-{version}-{release}.{arch}.rpm'
        return content.Artifact.create_or_update({
            'rpm_id': id,
            'archive_id': '0',
            'architecture': arch,
            'checksum': checksum,
            'filename': filename})[0]

    def get_or_create_rpm_artifact_from_rpm_info(self, rpm_info):
        """Fetch or create an Artifact from a dict of brew values."""
        return self.get_or_create_rpm_artifact(
            id=rpm_info['id'],
            name=rpm_info['name'],
            version=rpm_info['version'],
            release=rpm_info['release'],
            arch=rpm_info['arch'],
            checksum=rpm_info['payloadhash'])

    def get_or_create_archive_artifact(self, archive_id, filename, arch, checksum):
        """Get or create an artifact for a brew archive."""
        return content.Artifact.create_or_update({
            'archive_id': archive_id,
            'rpm_id': '0',
            'architecture': arch,
            'checksum': checksum,
            'filename': filename})[0]

    def get_or_create_source_location(self, url, canonical_version):
        """Get or create a SourceLocation."""
        sl = source.SourceLocation.get_or_create({'url': url})[0]
        if canonical_version:
            sl.canonical_version = canonical_version
        return sl

    def get_or_create_component(self, canonical_namespace, canonical_name, canonical_type):
        """Get or create Component."""
        return source.Component.get_or_create({
            'canonical_namespace': canonical_namespace,
            'canonical_name': canonical_name,
            'canonical_type': canonical_type})[0]
