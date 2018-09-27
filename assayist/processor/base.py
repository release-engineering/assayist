# SPDX-License-Identifier: GPL-3.0+

from abc import ABC, abstractmethod
import json
import neomodel
import os

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
        neomodel.config.DATABASE_URL = config.DATABASE_URL
        neomodel.config.AUTO_INSTALL_LABELS = True
        # run the analyzer in a transaction
        neomodel.db.begin()
        try:
            self.run()
            log.debug("Analyzer completed successfully, committing.")
            neomodel.db.commit()
        except Exception as e:
            log.exception("Error encountered executing Analyzer, rolling back transaction.")
            neomodel.db.rollback()
            raise

    @abstractmethod
    def run(self):
        """Implement anlyzer code here in your subclass."""

    def read_metadata_file(self, FILE):
        """Read and return the specified json metadata file or an empty dict."""
        if os.path.isfile(FILE):
            with open(FILE, 'r') as f:
                return json.load(f)
        else:
            log.debug("File not found: %s, returning empty dict", FILE)
            return {}

    def get_or_create_build(self, build_id, build_type):
        """Get or create a build object."""
        build = content.Build.nodes.get_or_none(id_=build_id)
        if build:
            return build

        return content.Build(id_=build_id, type=build_type).save()

    def get_or_create_rpm_artifact(self, id, name, epoch, version, release, arch, checksum):
        """Fetch or create an Artifact for this rpm."""
        # treat empty epochs as zero for consistency
        epoch = epoch if epoch else '0'
        nevr = f"{name}-{epoch}:{version}-{release}"
        aid = f'rpm-{id}'
        artifact = content.Artifact.nodes.get_or_none(archive_id=aid)
        if artifact:
            return artifact

        return content.Artifact(
            architecture=arch,
            archive_id=aid,
            checksum=checksum,
            filename=nevr).save()

    def get_or_create_rpm_artifact_from_hash(self, rpm_info):
        """Fetch or create an Artifact from a dict of brew values."""
        return self.get_or_create_rpm_artifact(
            id=rpm_info['id'],
            name=rpm_info['name'],
            epoch=rpm_info['epoch'],
            version=rpm_info['version'],
            release=rpm_info['release'],
            arch=rpm_info['arch'],
            checksum=rpm_info['payloadhash'])

    def get_or_create_archive_artifact(self, archive_id, filename, arch, checksum):
        """Get or create an artifact for a brew archive."""
        aid = f'archive-{archive_id}'
        artifact = content.Artifact.nodes.get_or_none(archive_id=aid)
        if artifact:
            return artifact

        return content.Artifact(
            architecture=arch,
            archive_id=aid,
            checksum=checksum,
            filename=filename).save()

    def get_or_create_source_location(self, url, canonical_version):
        """Get or create a SourceLocation."""
        sl = source.SourceLocation.nodes.get_or_none(url=url)
        if sl:
            return sl
        return source.SourceLocation(url=url, canonical_version=canonical_version).save()

    def get_or_create_component(self, canonical_namespace, canonical_name, canonical_type):
        """Get or create Component."""
        component = source.Component.nodes.get_or_none(
            canonical_namespace=canonical_namespace,
            canonical_name=canonical_name,
            canonical_type=canonical_type)

        if component:
            return component

        return source.Component(
            canonical_namespace=canonical_namespace,
            canonical_name=canonical_name,
            canonical_type=canonical_type).save()
