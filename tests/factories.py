# SPDX-License-Identifier: GPL-3.0+

import uuid
from random import choice, randint

from assayist.common.models.content import Build, Artifact, ExternalArtifact, Checksum, UnknownFile
from assayist.common.models.source import SourceLocation, Component


class ModelFactory:
    """Model factory class to hold common methods."""

    build_ids = iter(range(1000, 2000))
    archive_ids = iter(range(10000, 11000))
    versions = iter('.'.join(list(str(version))) for version in range(100, 200))
    releases = iter('.'.join(list(str(release))) for release in range(10, 90))

    @classmethod
    def create(cls, **values):
        """Build and save a model.

        :param values: specific attributes and their values that override the defaults
        :return: model instance saved into the database
        :rtype: assayist.common.models.AssayistStructuredNode
        """
        return cls.build(**values).save()

    @classmethod
    def generate_internal_git_url(cls, name, type_):
        """Generate an internal Git URL.

        :param name: name of the component in the URL
        :param type_: type of the component (e.g. rpm, container)
        :return: internal Git URL
        :rtype: str
        """
        return f'git://pkgs.domain.local/{type_}/{name}#{uuid.uuid4().hex}'

    @classmethod
    def generate_rpm_filename(cls, name=None, version=None, release=None, arch='noarch'):
        """Generate an RPM file name.

        :param name: name of the package
        :param version: version number of the package
        :param release: release number of the package
        :param arch: architecture of the package
        :return: RPM filename
        :rtype: str
        """
        filename = '{name}-{version}-{release}.{arch}.rpm'.format(
            name=name or choice('gcc firewalld firefox vim'.split()),
            version=version or next(cls.versions),
            release=release or next(cls.releases),
            arch=arch,
        )
        return filename

    @classmethod
    def generate_maven_gav(cls, g_id=None, a_id=None, version=None):
        """Generate a Maven GAV.

        :param g_id: group ID
        :param a_id: artifact ID
        :param version: version ID
        :return: Maven GAV
        :rtype: str
        """
        version = version or next(cls.versions)
        gav_data = choice(
            (
                ('com.redhat.fuse.eap', 'fuse-eap-installer', version + '.fuse-000008-redhat-3'),
                ('com.redhat.fuse.eap', 'fuse-eap', version + '.fuse-000008-redhat-3'),
                ('com.redhat.gss', 'redhat-support-lib-java', version + '-1'),
                ('com.redhat.lightblue.client', 'lightblue-client-core', version + '-1'),
            )
        )

        gav = '{group_id}-{artifact_id}-{version}'.format(
            group_id=g_id or gav_data[0],
            artifact_id=a_id or gav_data[1],
            version=version,
        )

        return gav


class BuildFactory(ModelFactory):
    """Factory class for Build model instances."""

    @classmethod
    def build(cls, **values):
        """Create an instance of a Build model.

        :param values: specific attributes and their values that override the defaults
        :return: model instance with filled-in data
        :rtype: assayist.common.models.content.Build
        """
        data = {
            'id_': str(next(cls.build_ids)),
            'type_': choice('container rpm maven'.split()),
        }

        data.update(values)
        return Build(**data)


class ArtifactFactory(ModelFactory):
    """Factory class for Artifact model instances."""

    ARCHITECTURES = 'aarch64 i686 ppc64le x86_64 s390x'.split()

    @classmethod
    def build(cls, **values):
        """Create an instance of an Artifact model.

        :param values: specific attributes and their values that override the defaults
        :return: model instance with filled-in data
        :rtype: assayist.common.models.content.Artifact
        """
        artifact_type = values.pop('type_', choice(list(Artifact.TYPES.keys())))

        if artifact_type == 'rpm':
            arch = choice(cls.ARCHITECTURES)
            data = {
                'architecture': arch,
                'filename': cls.generate_rpm_filename(arch=arch),
            }

        elif artifact_type == 'srpm':
            data = {
                'architecture': 'src',
                'filename': cls.generate_rpm_filename(arch='src'),
            }

        elif artifact_type == 'container':
            arch = choice(cls.ARCHITECTURES)
            data = {
                'architecture': arch,
                'filename': f'docker-image-sha256:{uuid.uuid4().hex}.{arch}.tar.gz',
            }

        elif artifact_type == 'maven':
            data = {
                'architecture': 'noarch',
                'filename': cls.generate_maven_gav() + '.jar'
            }

        elif artifact_type == 'other':
            data = {
                'architecture': 'noarch',
                'filename': cls.generate_maven_gav() + '.pom'
            }

        data['type_'] = artifact_type
        data['archive_id'] = str(next(cls.archive_ids))
        data.update(values)

        return Artifact(**data)


class ExternalArtifactFactory(ModelFactory):
    """Factory class for ExternalArtifact model instances."""

    IDENTIFIERS = (
        'org.commonjava.cdi.util:weft:jar:',
        'org.helloworld.util:hello:jar:',
        'com.sun.image.util:imager:jar:',
    )

    @classmethod
    def build(cls, **values):
        """Create an instance of an ExternalArtifact model.

        :param values: specific attributes and their values that override the defaults
        :return: model instance with filled-in data
        :rtype: assayist.common.models.content.ExternalArtifact
        """
        data = {
            'identifier': choice(cls.IDENTIFIERS) + next(cls.versions),
            'type_': 'maven',
        }

        data.update(values)
        return ExternalArtifact(**data)


class ChecksumFactory(ModelFactory):
    """Factory class for Checksum model instances."""

    @classmethod
    def build(cls, **values):
        """Create an instance of a Checksum model.

        :param values: specific attributes and their values that override the defaults
        :return: model instance with filled-in data
        :rtype: assayist.common.models.content.Checksum
        """
        data = {
            'algorithm': choice('sha1 sha256 sha512 md5'.split()),
            'checksum': uuid.uuid4().hex,
            'checksum_source': choice(list(Checksum.CHECKSUM_SOURCES.keys())),
        }

        data.update(values)
        return Checksum(**data)


class UnknownFileFactory(ModelFactory):
    """Factory class for UnknownFile model instances."""

    @classmethod
    def build(cls, **values):
        """Create an instance of a UnknownFile model.

        :param values: specific attributes and their values that override the defaults
        :return: model instance with filled-in data
        :rtype: assayist.common.models.content.UnknownFile
        """
        data = {
            'checksum': uuid.uuid4().hex,
            'filename': choice('where-did-this-come-from.sh another-one.py hello.txt'.split()),
            'path': choice('/bin /usr/local/bin /some/path'.split()),
        }

        data.update(values)
        return UnknownFile(**data)


class SourceLocationFactory(ModelFactory):
    """Factory class for SourceLocation model instances."""

    @classmethod
    def build(cls, **values):
        """Create an instance of a SourceLocation model.

        :param values: specific attributes and their values that override the defaults
        :return: model instance with filled-in data
        :rtype: assayist.common.models.source.SourceLocation
        """
        version = next(cls.versions)
        urls = (
            ModelFactory.generate_internal_git_url('etcd', 'containers'),
            ModelFactory.generate_internal_git_url('rsyslog', 'rpm'),
            f'https://github.com/coreos/etcd/archive/{uuid.uuid4().hex}/etcd-1674e682.tar.gz',
            f'http://yum.baseurl.org/download/yum-utils/yum-utils-{version}.tar.gz',
        )

        data = {
            'canonical_version': version,
            'url': choice(urls),
        }

        data.update(values)
        return SourceLocation(**data)


class ComponentFactory(ModelFactory):
    """Factory class for Component model instances."""

    # TODO: why is canonical-namespace required?
    COMPONENTS = {
        'requests': ('', 'requests', 'pypi', ['python3-requests', 'python-requests']),
        'configmap-reload': ('github.com/jimmidyson', 'configmap-reload', 'golang', []),
        'fsnotify': ('gopkg.in', 'fsnotify', 'golang', []),
        'sys': ('golang.org/x', 'sys', 'golang', []),
        'commonjava': ('', 'org.commonjava:commonjava-parent', 'maven', []),
        'etcd': ('github.com/coreos', 'etcd', 'golang', []),
        'bash': ('', 'bash', 'generic', []),
        'yum-utils': ('', 'yum-utils', 'generic', []),
        'rsyslog': ('', 'rsyslog', 'generic', []),
        'com.redhat.lightblue.client-lightblue-client-core': (
            '', 'com.redhat.lightblue.client:lightblue-client-core', 'maven', []
        ),
        'com.redhat.fuse.eap-fuse-eap': (
            '', 'com.redhat.fuse.eap:fuse-eap', 'maven', []
        ),
        'rsyslog-container': ('', 'rsyslog-container', 'docker', []),
        'openshift-enterprise-base-container': (
            '', 'openshift-enterprise-base-container', 'docker', []
        ),
        'atomic-openshift-metrics-server-container': (
            '', 'atomic-openshift-metrics-server-container', 'docker', []
        ),
        'jboss-eap-7-eap71': ('', 'jboss-eap-7-eap71', 'docker', []),
    }

    @classmethod
    def build(cls, name=None, **values):
        """Create an instance of a Component model.

        :param name: specific component from the COMPONENTS dict
        :param values: specific attributes and their values that override the defaults
        :return: model instance with filled-in data
        :rtype: assayist.common.models.source.Component
        """
        component = cls.COMPONENTS[name] if name else choice(tuple(cls.COMPONENTS.keys()))
        component_attrs = ('canonical_namespace', 'canonical_name', 'canonical_type',
                           'alternative_names')
        data = dict(zip(component_attrs, component))

        data.update(values)
        return Component(**data)


class UseCaseFactory:
    """Factory class to compose graph scenarios with several different models.

    Each use case can be modified to return data expected by tests that use them.
    """

    @classmethod
    def _container_build(cls, name, create_component=True):
        """Create a set of container build models.

        :param name: specific name of the container (e.g. ``rsyslog-container``)
        :param create_component: determines whether to create a component or not
        :return: A tuple of relevant container build resources
        :rtype: (Component, SourceLocation, Build, Artifact)
        """
        if create_component:
            container_component = ComponentFactory.create(name=name)
        else:
            container_component = None

        container_build = BuildFactory.create(type_='container')
        container_artifact = ArtifactFactory.create(type_='container')
        container_build.artifacts.connect(container_artifact)

        container_sl = SourceLocationFactory.create(
            url=ModelFactory.generate_internal_git_url(name, 'containers'),
            canonical_version=None,
        )
        container_build.source_location.connect(container_sl)

        if container_component:
            container_sl.component.connect(container_component)

        for _ in range(randint(0, 2)):
            unknown_file = UnknownFileFactory.create()
            container_artifact.unknown_files.connect(unknown_file)

        return container_component, container_sl, container_build, container_artifact

    @classmethod
    def _rpm_build(cls, name, version, upstream_url=None, create_component=True):
        """Create a set of RPM models.

        :param name: name of the built RPM (e.g. 'rsyslog')
        :param version: version of the built RPM (e.g. '1.0.0')
        :param upstream_url: URL of the upstream SourceLocation
        :param create_component: determines whether to create a component or not
        :return: A tuple of relevant RPM build resources
        :rtype: (Build, Artifact, Component, SourceLocation, SourceLocation)
        """
        if create_component:
            rpm_component = ComponentFactory.create(name=name)
        else:
            rpm_component = None

        if upstream_url:
            rpm_upstream_sl = SourceLocationFactory.create(url=upstream_url, version=version)
        else:
            rpm_upstream_sl = None

        rpm_internal_sl = SourceLocationFactory.create(
            url=ModelFactory.generate_internal_git_url(name, 'rpm'),
        )

        rpm_build = BuildFactory.create(type_='rpm')
        rpm_artifact = ArtifactFactory.create(
            type_='rpm',
            filename=ModelFactory.generate_rpm_filename(name=name, version=version),
        )
        rpm_checksum = ChecksumFactory.create()

        rpm_build.artifacts.connect(rpm_artifact)
        rpm_artifact.checksums.connect(rpm_checksum)
        rpm_build.source_location.connect(rpm_internal_sl)

        if rpm_component:
            rpm_internal_sl.component.connect(rpm_component)

        if upstream_url:
            rpm_internal_sl.upstream.connect(rpm_upstream_sl)

            if rpm_component:
                rpm_upstream_sl.component.connect(rpm_component)

        for _ in range(randint(0, 2)):
            unknown_file = UnknownFileFactory.create()
            rpm_artifact.unknown_files.connect(unknown_file)

        return rpm_build, rpm_artifact, rpm_component, rpm_upstream_sl, rpm_internal_sl

    @classmethod
    def _maven_build(cls, g_id, a_id, upstream_url=None):
        """Create a set of Maven models.

        :param g_id: Maven group ID
        :param a_id: Maven artifact ID
        :param upstream_url: URL of the upstream SourceLocation
        :return: A Maven artifact
        :rtype: Artifact
        """
        maven_component = ComponentFactory.create(name=f'{g_id}-{a_id}')

        maven_internal_sl = SourceLocationFactory.create(
            url=ModelFactory.generate_internal_git_url(maven_component.canonical_name, 'maven'),
        )

        if upstream_url:
            maven_upstream_sl = SourceLocationFactory.create(
                url=upstream_url,
                version=maven_internal_sl.canonical_version,
            )
        else:
            maven_upstream_sl = None

        maven_build = BuildFactory.create(type_='maven')
        maven_artifact = ArtifactFactory.create(
            type_='maven',
            filename=ModelFactory.generate_maven_gav(g_id=g_id, a_id=a_id),
        )
        maven_checksum = ChecksumFactory.create()

        maven_build.artifacts.connect(maven_artifact)
        maven_artifact.checksums.connect(maven_checksum)
        maven_build.source_location.connect(maven_internal_sl)
        maven_internal_sl.component.connect(maven_component)

        if maven_upstream_sl:
            maven_internal_sl.upstream.connect(maven_upstream_sl)
            maven_upstream_sl.component.connect(maven_component)

        for _ in range(randint(0, 2)):
            unknown_file = UnknownFileFactory.create()
            maven_artifact.unknown_files.connect(unknown_file)

        for _ in range(randint(0, 2)):
            ext_artifact = ExternalArtifactFactory.create()
            maven_artifact.embedded_external_artifacts.connect(ext_artifact)

        return maven_artifact

    @classmethod
    def container_with_rpm_artifacts(cls):
        """Create a container build that embeds two RPMs each with their own builds.

        See ./images/container_with_rpm_artifacts.png for a visual representation of this use case.

        :return: A tuple containing the build ID, a list of internal SourceLocation URLs,
                 and a list of external SourceLocation URLs.
        :rtype: (int, list, list)
        """
        _, etcd_rpm, _, etcd_upstream_sl, etcd_internal_sl = cls._rpm_build(
            'etcd', '3.2.22',
            'https://github.com/coreos/etcd/archive/1674e682f/etcd-1674e682.tar.gz',
        )

        _, yum_utils_rpm, _, yum_utils_upstream_sl, yum_utils_internal_sl = cls._rpm_build(
            'yum-utils', '1.1.31',
            'http://yum.baseurl.org/download/yum-utils/yum-utils-1.1.31.tar.gz',
        )

        _, _, container_build, container_artifact = cls._container_build(
            'openshift-enterprise-base-container')
        container_artifact.embedded_artifacts.connect(etcd_rpm)
        container_artifact.embedded_artifacts.connect(yum_utils_rpm)

        return (container_build.id_,
                [yum_utils_internal_sl.url, etcd_internal_sl.url],
                [yum_utils_upstream_sl.url, etcd_upstream_sl.url])

    @classmethod
    def container_with_preceding_rpm_versions(cls):
        """Create two container builds that each embed a different version of the same RPM.

        See ./images/container_with_preceding_rpm_versions.png for a visual representation of
        this use case.
        """
        _, rsyslog_rpm, rsyslog_comp, rsyslog_upstream_sl, rsyslog_internal_sl = cls._rpm_build(
            'rsyslog', '7.6.7',
            'http://www.rsyslog.com/files/download/rsyslog/rsyslog-7.6.7.tar.gz',
        )

        _, rsyslog_next_rpm, _, rsyslog_next_upstream_sl, rsyslog_next_internal_sl = cls._rpm_build(
            'rsyslog', '7.6.8',
            'http://www.rsyslog.com/files/download/rsyslog/rsyslog-7.6.8.tar.gz',
            create_component=False
        )

        rsyslog_next_upstream_sl.component.connect(rsyslog_comp)
        rsyslog_next_internal_sl.component.connect(rsyslog_comp)

        rsyslog_container_component, _, rsyslog_container_build, rsyslog_container_artifact = \
            cls._container_build('rsyslog-container')
        _, rsyslog_next_container_sl, rsyslog_next_container_build, rsyslog_next_container_artifact\
            = cls._container_build('rsyslog-container', create_component=False)

        rsyslog_next_container_sl.component.connect(rsyslog_container_component)

        rsyslog_container_artifact.embedded_artifacts.connect(rsyslog_rpm)
        rsyslog_next_container_artifact.embedded_artifacts.connect(rsyslog_next_rpm)

        rsyslog_next_internal_sl.previous_version.connect(rsyslog_internal_sl)
        rsyslog_next_upstream_sl.previous_version.connect(rsyslog_upstream_sl)

    @classmethod
    def container_with_maven_artifacts(cls):
        """Create a container that embeds two layers of embedded Maven artifacts.

        See ./images/container_with_maven_artifacts.png for a visual representation of this use
        case.
        """
        lightblue_artifact = cls._maven_build(
            g_id='com.redhat.lightblue.client', a_id='lightblue-client-core',
            upstream_url='http://www.lightblue.org/dl/lightblue.jar'
        )

        fuse_artifact = cls._maven_build(
            g_id='com.redhat.fuse.eap', a_id='fuse-eap',
        )
        fuse_artifact.embedded_artifacts.connect(lightblue_artifact)
        fuse_artifact

        _, _, _, eap_container = cls._container_build('jboss-eap-7-eap71')
        eap_container.embedded_artifacts.connect(fuse_artifact)

    @classmethod
    def container_with_go_and_rpm_artifacts(cls):
        """Create a container that embeds an RPM, a parent container, and Go sources.

        The parent container also embeds its own RPM.

        See ./images/container_with_go_and_rpm_artifacts.png for a visual representation of this
        use case.
        """
        _, bash_rpm, _, _, _ = cls._rpm_build(
            'bash', '4.2.47',
            'ftp://ftp.gnu.org/gnu/bash/bash-4.2.46.tar.gz',
        )

        _, etcd_rpm, _, _, _ = cls._rpm_build(
            'etcd', '3.2.22',
            'https://github.com/coreos/etcd/archive/65b4dd7c/etcd-65b4dd7c.tar.gz',
        )

        cls._rpm_build('etcd', '3.2.20')  # unused RPM build

        _, _, _, parent_container = cls._container_build('openshift-enterprise-base-container')
        parent_container.embedded_artifacts.connect(bash_rpm)

        _, container_sl, _, container = cls._container_build(
            'atomic-openshift-metrics-server-container',
        )
        container.embedded_artifacts.connect(parent_container)
        container.embedded_artifacts.connect(etcd_rpm)

        go_sources = (
            ('configmap-reload', 'https://github.com/jimmidyson/configmap-reload', 'v0.2.2'),
            ('fsnotify', 'https://gopkg.in/fsnotify.v1', 'v1.4.7'),
            ('sys', 'https://go.googlesource.com/sys', 'v0.0.0-0.20150901164945-9c60d1c508f5'),
        )

        for name, url, version in go_sources:
            sl = SourceLocationFactory.create(url=url, canonical_version=version)
            sl.component.connect(ComponentFactory.create(name=name))
            if 'configmap-reload' in url:
                container_sl.upstream.connect(sl)
            else:
                container_sl.embedded_source_locations.connect(sl)
