# SPDX-License-Identifier: GPL-3.0+

from abc import ABC, abstractmethod
from functools import cmp_to_key
import json
import os

from hashlib import sha256
from neomodel import db, ZeroOrOne, One
from pkg_resources import parse_version
import rpm

from assayist.common.models import content, source
from assayist.processor.configuration import config
from assayist.processor.logging import log
from assayist.processor.utils import get_koji_session

BLOCKSIZE = 65536


def rpm_compare(x, y):
    """
    Compare two rpm canonical_versions.

    :param SourceLocation x: The first SourceLocation to compare
    :param SourceLocation y: The second SourceLocation to compare
    :return: -1, 0, or 1 as required by standard comparison methods.
    :rtype: int
    """
    # By definition, see _construct_and_save_component.
    x_values = x.canonical_version.split('-')
    y_values = y.canonical_version.split('-')
    # If we're evaluating a container then fake out a zero EPOCH.
    if len(x_values) == 2:
        x_values = ['0'] + x_values
        y_values = ['0'] + y_values
    return rpm.labelCompare(x_values, y_values)


rpm_key = cmp_to_key(rpm_compare)


def generic_key(x):
    """
    Evaluate to a comparable generic version.

    :param Component x: The version in question
    :return: Some type of comparable object
    :rtype: Object
    """
    return parse_version(x.canonical_version)


class Analyzer(ABC):
    """Base Abstract class that analyzers will inherit from."""

    # Directory paths, relative to input_dir
    METADATA_DIR = 'metadata'
    FILES_DIR = 'output_files'
    SOURCE_DIR = 'source'
    UNPACKED_ARCHIVES_DIR = 'unpacked_archives'
    UNPACKED_CONTAINER_LAYER_DIR = os.path.join(UNPACKED_ARCHIVES_DIR,
                                                'container_layer')

    # Metadata files (use with read_metadata_file)
    BUILD_FILE = 'buildinfo.json'
    TASK_FILE = 'taskinfo.json'
    MAVEN_FILE = 'maveninfo.json'
    RPM_FILE = 'rpms.json'
    ARCHIVE_FILE = 'archives.json'
    IMAGE_RPM_FILE = 'image-rpms.json'
    BUILDROOT_FILE = 'buildroot-components.json'

    # The following is a list of build types (indicated by the task method linked to the build),
    # for which we support running all of the analyzers. All other build types will have their
    # Build node created but further analysis will be skipped. This list may be extended with
    # additional types when we can assure that they can be accurately analyzed and their artifacts
    # correctly processed.
    #
    # When a new type is added, ensure the _construct_and_save_component() function is updated to
    # handle the new type.
    CONTAINER_BUILD_TYPE = 'buildContainer'
    RPM_BUILD_TYPE = 'build'
    WRAPPER_RPM_BUILD_TYPE = 'wrapperRPM'  # RPM builds used in other builds
    MAVEN_BUILD_TYPE = 'maven'
    SUPPORTED_BUILD_TYPES = (
        CONTAINER_BUILD_TYPE,
        RPM_BUILD_TYPE,
        WRAPPER_RPM_BUILD_TYPE,
        MAVEN_BUILD_TYPE,
    )
    SUPPORTED_RPM_BUILD_TYPES = (
        RPM_BUILD_TYPE,
        WRAPPER_RPM_BUILD_TYPE,
    )

    def __init__(self, input_dir='/'):
        """
        Initialize the Analyzer class.

        :param str input_dir: The directory in which to find the files.
        """
        self.input_dir = input_dir
        self._koji_session = None

    def main(self):
        """Call this to run the analyzer."""
        db.set_connection(config.DATABASE_URL)
        self.run()

    @abstractmethod
    def run(self):
        """Implement analyzer code here in your subclass."""

    @property
    def koji_session(self):
        """Return a cached Koji session and create it if necessary."""
        if self._koji_session is None:
            self._koji_session = get_koji_session()
        return self._koji_session

    def read_metadata_file(self, in_file):
        """
        Read and return the specified json metadata file or an empty dict.

        :param str in_file: The name of the input file to read. Probably one of the class constants.
        :return: a dict or list read from the file, or an empty dict
        :rtype: {}
        :raises ValueError: if the file was not valid json content
        """
        filename = os.path.join(self.input_dir, self.METADATA_DIR, in_file)
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

    def create_or_update_archive_artifact_from_archive_info(self, archive_info):
        """
        Create or update an Artifact for this archive from a dictionary.

        :param dict archive_info: A dictionary of information, like one that comes from brew.
                                  Must contain the fields used in create_or_update_archive_artifact.
        :return: an Artifact object
        :rtype: assayist.common.models.content.Artifact
        """
        archive_id = archive_info['id']
        _type = archive_info['btype']
        checksum = archive_info['checksum']
        filename = archive_info['filename']

        # Find the nested arch information or set noarch. Note that 'extra' can exist
        # and be set to None in real data, so you can't chain all the gets.
        extra = archive_info.get('extra', {})
        if extra:
            arch = extra.get('image', {}).get('arch', 'noarch')
        else:
            arch = 'noarch'

        return self.create_or_update_archive_artifact(archive_id, filename, arch, _type, checksum)

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

    @db.transaction
    def create_or_update_source_location(self, url, component, canonical_version=None):
        """
        Create or update SourceLocation.

        Connect it to the component provided.
        If canonical_version is provided link it with similar SourceLocations via SUPERSEDES.
        This method runs in a transaction to prevent concurrent modification from breaking the
        SUPERSEDES chain.

        :param str url: the url and possibly commit hash of the source location
        :param Component component: the component associated with this SourceLocation
        :param str canonical_version: (optional) the version of the component that
                                      corresponds with this commit id
        :return: a SourceLocation object
        :rtype: assayist.common.models.source.SourceLocation
        """
        # Figure out what type of SourceLocation we're dealing with.
        sl_type = ''
        if canonical_version:
            # TODO: A better determination?
            if '.redhat.com/' in url:
                sl_type = 'local'
            else:
                sl_type = 'upstream'

        # Get it.
        sl = source.SourceLocation.create_or_update({
            'url': url,
            'type_': sl_type})[0]

        # It's possible that component is None
        if not component:
            return sl.save()

        if canonical_version:
            sl.canonical_version = canonical_version

            # Find all SLs related to this component of the same type.
            # There is a match() function, but it only works if the relationship has a model.
            similar_source_locations = component.source_locations.filter(
                type_=sl_type, canonical_version__isnull=False).all()

            # Find our place in the chain, which may be beginning, middle, or end.
            # Note that I'm assuming that these are all in the chain. Which they should be.
            if sl not in similar_source_locations:
                similar_source_locations.append(sl)

            if component.canonical_type in ('rpm', 'docker'):
                # Containers use the version-release system from brew,
                # so they need to be evaluated rpmishly too.
                key_method = rpm_key
            else:
                key_method = generic_key
            similar_source_locations.sort(key=key_method)

            # Insert this SourceLocation in the appropriate place in the graph.
            index = similar_source_locations.index(sl)
            if index > 0:
                self.conditional_connect(similar_source_locations[index - 1].next_version, sl)
            if (index + 1) < len(similar_source_locations):
                self.conditional_connect(similar_source_locations[index + 1].previous_version, sl)

        # Finally connect to the component, save, and return.
        self.conditional_connect(sl.component, component)
        return sl.save()

    def claim_file(self, base_dir, path_in_base_dir):
        """
        Claim (delete) a file in the base directory.

        This method is used by analyzers to claim a file they've identified. All directories are
        silently ignored.

        :param str base_dir: the base directory to claim a file from
        :param str path_in_base_dir: the path to the file in the base directory to claim
        :raises RuntimeError: when the path to the base_dir is not a directory
        """
        if path_in_base_dir == '/':
            return

        file_path = path_in_base_dir.lstrip('/')

        if not os.path.isdir(base_dir):
            raise RuntimeError(f'The path "{base_dir}" is not a directory')

        abs_base_dir = os.path.abspath(base_dir)

        def _resolve_path(target):
            """Resolve the first symbolic link in the path recursively."""
            current_path = target
            # Crawl upwards starting at the target until the base directory is reached
            while current_path != abs_base_dir:
                if os.path.islink(current_path):
                    # Get the absolute path of the link's target but strip the starting slash
                    link_target = os.path.abspath(os.readlink(current_path))[1:]
                    # Find the path after the link, for instance, if the link is
                    # `/opt/rh/httpd24/root/etc/httpd` => `/etc/httpd`, and the passed in target is
                    # `/opt/rh/httpd24/root/etc/httpd/httpd.conf`, then we just want `httpd.conf`.
                    path_after_link = os.path.relpath(target, current_path)
                    # The resolved path for the above example would be the base directory plus
                    # `etc/httpd/httpd.conf`
                    resolved_path = os.path.join(abs_base_dir, link_target, path_after_link)
                    # In case there is more than one link in the path, call this closure again
                    return _resolve_path(resolved_path)
                current_path = os.path.dirname(current_path)
            # No links were found, so just return the target
            return target

        resolved_path = _resolve_path(os.path.join(abs_base_dir, file_path))
        if os.path.isdir(resolved_path):
            log.debug(f'Ignoring "{resolved_path}" since directories don\'t get claimed')
        elif os.path.isfile(resolved_path):
            log.debug(f'Claiming file "{resolved_path}"')
            os.remove(resolved_path)

    def claim_container_file(self, container_archive, path_in_container):
        """
        Claim (delete) a file in the extracted container.

        This method is used by analyzers to claim a file they've identified. All directories are
        silently ignored.

        :param str container_archive: the container archive to claim the file from
        :param str path_in_container: the path to the file in the container to claim
        :raises RuntimeError: when path_in_container is the root directory or the path to the
            extracted container layer is not a directory
        """
        container_layer_dir = os.path.join(
            self.input_dir, self.UNPACKED_CONTAINER_LAYER_DIR,
            container_archive['filename'])
        self.claim_file(container_layer_dir, path_in_container)

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

    @staticmethod
    def conditional_connect(relationship, new_node):
        """
        Wrap the connect and replace methods for conditional relationship handling.

        "Borrowed" from https://github.com/release-engineering/estuary-api
        /blob/master/estuary/models/base.py#L152

        :param neomodel.RelationshipManager relationship: a relationship to connect on
        :param neomodel.StructuredNode new_node: the node to create the relationship with
        :raises NotImplementedError: if this method is called with a relationship of cardinality of
        one
        """
        if new_node not in relationship:
            if len(relationship) == 0:
                relationship.connect(new_node)
            else:
                if isinstance(relationship, ZeroOrOne):
                    relationship.replace(new_node)
                elif isinstance(relationship, One):
                    raise NotImplementedError(
                        'conditional_connect doesn\'t support cardinality of one')
                else:
                    relationship.connect(new_node)

    @staticmethod
    def checksum(filename, method=sha256):  # pragma: no cover
        """Create a checksum for a (potentially large) file.

        :param str filename: path to the file being checksummed
        :param function method: the hashlib checksum function to use, default: sha256
        :return: checksum
        :rtype: str
        """
        func = method()
        with open(filename, 'rb') as f:
            buffer = f.read(BLOCKSIZE)
            while len(buffer) > 0:
                func.update(buffer)
                buffer = f.read(BLOCKSIZE)

        return func.hexdigest()

    @staticmethod
    def walk(top, extensions=None):
        """
        Walk the directories under top, generating all paths to the files.

        If a list of extensions is provided results are limited to only those endings.
        Note that this method does not follow symlinks, which is desired. We were getting
        stuck following near-infinite loops (limited by MAX_PATH) following symlink loops.
        Use only for applications where it is only important that you find all files, not
        where you need to have found all paths to all files.

        :param str top: path to the directory that is the root of the search
        :param list extensions: A list of extensions to limit the results with. If None
                                (default) all files will be returned. Example:
                                ['.rpm', '.tar.gz']
        :return: Iterable of byte-string paths to the files.
        :rtype: Iterable
        """
        if extensions:
            extensions = tuple(extensions)  # don't know why, but it has to be a tuple

        for path, dirs, files in os.walk(top):
            for f in os.scandir(path):
                if f.is_file(follow_symlinks=False) and (not extensions or
                                                         f.name.endswith(extensions)):
                    yield f.path
