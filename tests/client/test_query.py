# SPDX-License-Identifier: GPL-3.0+

from assayist.client import query
from assayist.common.models.content import Build, Artifact
from assayist.common.models.source import SourceLocation, Component


def test_get_container_by_component():
    """Test the get_container_by_component function with a container that includes a component."""
    # Create the container build entry
    c_build = Build(id_='123456', type_='container').save()

    c_filename = ('docker-image-sha256:98217b7c89052267e1ed02a41217c2e03577b96125e923e9594'
                  '1ac010f209ee6.x86_64.tar.gz')
    c_artifact = Artifact(
        archive_id='742663', architecture='x86_64', filename=c_filename,
        type_='container'
    ).save()
    c_build.artifacts.connect(c_artifact)

    c_internal_url = ('git://pks.domain.local/containers/rsyslog#'
                      '3dcd6fc75e674589ac7d2294dbf79bd8ebd459fb')
    c_internal_source = SourceLocation(url=c_internal_url).save()
    c_build.source_location.connect(c_internal_source)

    rpm_internal_source_url = (
        'git://pkgs.devel.redhat.com/rpms/rsyslog#5d99244f963e634c60b458c0c2884ee63d7e8827'
    )
    rpm_internal_source = SourceLocation(url=rpm_internal_source_url).save()

    rpm_upstream_url = 'http://www.rsyslog.com/files/download/rsyslog/rsyslog-7.6.7.tar.gz'
    rpm_upstream_source = SourceLocation(url=rpm_upstream_url, canonical_version='7.6.7',
                                         canonical_type='generic').save()
    rpm_internal_source.upstream.connect(rpm_upstream_source)

    rpm_component = Component(canonical_name='rsyslog', canonical_type='generic',
                              canonical_namespace='').save()
    rpm_upstream_source.component.connect(rpm_component)
    rpm_internal_source.component.connect(rpm_component)

    rpm_artifact = Artifact(
        archive_id='760135', architecture='x86_64', filename='rsyslog-8.24.0-34.el7.x86_64.rpm',
        type_='rpm'
    ).save()

    rpm_build = Build(id_='789012', type_='rpm').save()
    rpm_build.artifacts.connect(rpm_artifact)
    rpm_build.source_location.connect(rpm_internal_source)

    c_artifact.embedded_artifacts.connect(rpm_artifact)

    assert query.get_container_by_component('rsyslog', 'generic', '7.6.7') == {123456}


def test_get_container_by_embedded_component():
    """Test the get_container_by_component function with a container that embeds a component."""
    # Set up a layered container image build, container_build, whose
    # single image embeds an RPM and a Go executable. Its parent image
    # also embeds an RPM.
    #
    # First, a parent image, parent:
    #   (parent:Artifact) <-- (:Build) <-- (:SourceLocation)
    # Then the container itself, image:
    #   (image:Artifact) <-- (container_build:Build) <-- (:SourceLocation)
    #   (a:Artifact) <-[:EMBEDS]- (parent:Artifact)
    #
    # And let's have the parent image embed an RPM, bash:
    #   (parent:Artifact) <-[:EMBEDS]- (bash_rpm:Artifact)
    #       <-- (:Build) <-- (bash_internal_source:SourceLocation)
    #       <-- (bash_upstream_source:SourceLocation) <-- (:Component)

    # bash RPM for parent image
    bash_build = Build(id_='1000', type_='rpm').save()
    bash_rpm = Artifact(
        archive_id='1001',
        architecture='x86_64',
        filename='bash-4.2.46-30.el7.x86_64.rpm',
        type_='rpm').save()
    bash_build.artifacts.connect(bash_rpm)
    bash_upstream_url = 'ftp://ftp.gnu.org/gnu/bash/bash-4.2.46.tar.gz'
    bash_upstream_source = SourceLocation(url=bash_upstream_url, canonical_type='generic',
                                          canonical_version='4.2.46').save()
    bash_internal_url = 'git://pkgs.domain.local/rpms/bash#5f22bafc903fd0343640a6d7e25c87e32e504b9c'
    bash_internal_source = SourceLocation(url=bash_internal_url).save()
    bash_build.source_location.connect(bash_internal_source)
    bash_internal_source.upstream.connect(bash_upstream_source)
    bash_component = Component(canonical_type='generic', canonical_namespace='',
                               canonical_name='bash').save()
    bash_upstream_source.component.connect(bash_component)

    # Parent image
    parent_build = Build(id_='2000', type_='container').save()
    container_filename = 'docker-image-sha256:' + '0' * 64 + '.x86_64.tar.gz'
    parent = Artifact(
        archive_id='2001',
        architecture='x86_64',
        filename=container_filename,
        type_='container').save()
    parent_build.artifacts.connect(parent)
    container_internal_url = 'git://pkgs.domain.local/containers/parent#...'
    container_internal_source = SourceLocation(url=container_internal_url).save()
    parent_build.source_location.connect(container_internal_source)
    parent.embedded_artifacts.connect(bash_rpm)  # bash RPM is installed

    # etcd RPM for container image we'll query
    etcd_build = Build(id_='3000', type_='rpm').save()
    etcd_rpm = Artifact(
        archive_id='3001',
        architecture='x86_64',
        filename='etcd-3.2.22-1.el7.x86_64.rpm',
        type_='rpm').save()
    etcd_build.artifacts.connect(etcd_rpm)

    # Add an additional architecture that is not used by the build
    # we'll query about. This is to test we are not selecting
    # artifacts we should not be.
    etcd_unused_rpm = Artifact(
        archive_id='3002',
        architecture='ppc64le',
        filename='etcd-3.2.22-1.el7.ppc64le.rpm',
        type_='rpm').save()
    etcd_build.artifacts.connect(etcd_unused_rpm)

    # Sources for etcd
    etcd_upstream_url = ('https://github.com/coreos/etcd/archive/'
                         '1674e682fe9fbecd66e9f20b77da852ad7f517a9/etcd-1674e68.tar.gz')
    etcd_upstream_source = SourceLocation(url=etcd_upstream_url,
                                          canonical_version='3.2.22').save()
    etcd_internal_url = 'git://pkgs.domain.local/rpms/etcd#84858fb38a89e1177b0303c675d206f90f6a83e2'
    etcd_internal_source = SourceLocation(url=etcd_internal_url).save()
    etcd_build.source_location.connect(etcd_internal_source)
    etcd_internal_source.upstream.connect(etcd_upstream_source)
    etcd_component = Component(canonical_type='github', canonical_namespace='coreos',
                               canonical_name='etcd').save()
    etcd_upstream_source.component.connect(etcd_component)

    # The container itself
    container_build = Build(id_='4000', type_='container').save()
    container_filename = 'docker-image-sha256:' + '1' * 64 + '.x86_64.tar.gz'
    image = Artifact(
        archive_id='4001',
        architecture='x86_64',
        filename=container_filename,
        type_='container').save()
    container_build.artifacts.connect(image)
    container_internal_url = 'git://pkgs.domain.local/containers/image#...'
    container_internal_source = SourceLocation(url=container_internal_url).save()
    container_build.source_location.connect(container_internal_source)
    image.embedded_artifacts.connect(parent)  # inherits from parent image
    image.embedded_artifacts.connect(etcd_rpm)  # etcd RPM is installed

    # Go executable
    # Based on output from backvendor:
    # *github.com/jimmidyson/configmap-reload@043045da[...] =v0.2.2 ~v0.2.2
    # golang.org/x/sys@9c60d1c[...] ~v0.0.0-0.20150901164945-9c60d1c508f5
    # gopkg.in/fsnotify.v1@c282820[...] =v1.4.7 ~v1.4.7
    configmap_reload = SourceLocation(url='https://github.com/jimmidyson/configmap-reload',
                                      canonical_version='v0.2.2').save()
    configmap_reload.component.connect(
        Component(canonical_type='golang',
                  canonical_namespace='github.com/jimmidyson',
                  canonical_name='configmap-reload').save())
    x_sys = SourceLocation(url='https://go.googlesource.com/sys',
                           canonical_version='v0.0.0-0.20150901164945-9c60d1c508f5').save()
    x_sys.component.connect(
        Component(canonical_type='golang',
                  canonical_namespace='golang.org/x',
                  canonical_name='sys').save())
    fsnotify = SourceLocation(url='https://gopkg.in/fsnotify.v1',
                              canonical_version='v1.4.7').save()
    fsnotify.component.connect(
        Component(canonical_type='golang',
                  canonical_namespace='gopkg.in',
                  canonical_name='fsnotify.v1').save())

    container_internal_source.upstream.connect(configmap_reload)
    container_internal_source.embedded_source_locations.connect(x_sys)
    container_internal_source.embedded_source_locations.connect(fsnotify)

    assert query.get_container_by_component('fsnotify.v1', 'golang', 'v1.4.7') == {4000}
    assert query.get_container_by_component('sys', 'golang',
                                            'v0.0.0-0.20150901164945-9c60d1c508f5') == {4000}
    assert query.get_container_by_component('configmap-reload', 'golang', 'v0.2.2') == {4000}
    assert query.get_container_by_component('bash', 'generic', '4.2.46') == {4000, 2000}


def test_get_container_sources():
    """Test the get_container_sources function."""
    # Create the container build entry
    container_build_id = '742663'
    container_build = Build(id_=container_build_id, type_='container').save()
    container_filename = ('docker-image-sha256:98217b7c89052267e1ed02a41217c2e03577b96125e923e9594'
                          '1ac010f209ee6.x86_64.tar.gz')
    container_artifact = Artifact(
        archive_id='742663',
        architecture='x86_64',
        filename=container_filename,
        type_='container').save()
    container_build.artifacts.connect(container_artifact)
    container_internal_url = ('git://pks.domain.local/containers/etcd#'
                              '3dcd6fc75e674589ac7d2294dbf79bd8ebd459fb')
    container_internal_source = SourceLocation(url=container_internal_url).save()
    container_build.source_location.connect(container_internal_source)

    # Create the embedded artifacts
    etcd_build = Build(id_='770188', type_='rpm').save()
    etcd_rpm = Artifact(
        archive_id='5818103',
        architecture='x86_64',
        filename='etcd-3.2.22-1.el7.x86_64.rpm',
        type_='rpm').save()
    etcd_build.artifacts.connect(etcd_rpm)
    etcd_upstream_url = ('https://github.com/coreos/etcd/archive/1674e682fe9fbecd66e9f20b77da852ad7'
                         'f517a9/etcd-1674e682.tar.gz')
    etcd_upstream_source = SourceLocation(url=etcd_upstream_url).save()
    etcd_internal_url = 'git://pks.domain.local/rpms/etcd#84858fb38a89e1177b0303c675d206f90f6a83e2'
    etcd_internal_source = SourceLocation(url=etcd_internal_url).save()
    etcd_build.source_location.connect(etcd_internal_source)
    etcd_internal_source.upstream.connect(etcd_upstream_source)
    container_artifact.embedded_artifacts.connect(etcd_rpm)

    yum_utils_build = Build(id_='728353', type_='rpm').save()
    yum_utils_rpm = Artifact(
        archive_id='5962202',
        architecture='x86_64',
        type_='rpm',
        filename='yum-utils-1.1.31-46.el7_5.noarch.rpm').save()
    yum_utils_build.artifacts.connect(yum_utils_rpm)
    yum_utils_upstream_url = 'http://yum.baseurl.org/download/yum-utils/yum-utils-1.1.31.tar.gz'
    yum_utils_upstream_source = SourceLocation(url=yum_utils_upstream_url).save()
    yum_utils_internal_url = ('git://pks.domain.local/rpms/yum-utils#562e476db1be88f58662d6eb3'
                              '82bb37e87bf5824')
    yum_utils_internal_source = SourceLocation(url=yum_utils_internal_url).save()
    yum_utils_build.source_location.connect(yum_utils_internal_source)
    yum_utils_internal_source.upstream.connect(yum_utils_upstream_source)
    container_artifact.embedded_artifacts.connect(yum_utils_rpm)

    expected = {
        'internal_urls': [yum_utils_internal_url, etcd_internal_url],
        'upstream_urls': [yum_utils_upstream_url, etcd_upstream_url]
    }
    assert query.get_container_content_sources(container_build_id) == expected


def test_get_source_components_for_build():
    """Test the get_source_components_for_build function."""
    # Set up a layered container image build, container_build, whose
    # single image embeds an RPM and a Go executable. Its parent image
    # also embeds an RPM.
    #
    # First, a parent image, parent:
    #   (parent:Artifact) <-- (:Build) <-- (:SourceLocation)

    # Then the container itself, image:
    #   (image:Artifact) <-- (container_build:Build) <-- (:SourceLocation)
    #   (a:Artifact) <-[:EMBEDS]- (parent:Artifact)
    #
    # And let's have the parent image embed an RPM, bash:
    #   (parent:Artifact) <-[:EMBEDS]- (bash_rpm:Artifact)
    #       <-- (:Build) <-- (bash_internal_source:SourceLocation)
    #       <-- (bash_upstream_source:SourceLocation) <-- (:Component)

    # bash RPM for parent image
    bash_build = Build(id_='1000', type_='rpm').save()
    bash_rpm = Artifact(
        archive_id='1001',
        architecture='x86_64',
        filename='bash-4.2.46-30.el7.x86_64.rpm',
        type_='rpm').save()
    bash_build.artifacts.connect(bash_rpm)
    bash_upstream_url = 'ftp://ftp.gnu.org/gnu/bash/bash-4.2.46.tar.gz'
    bash_upstream_source = SourceLocation(url=bash_upstream_url,
                                          canonical_version='4.2.46').save()
    bash_internal_url = 'git://pkgs.domain.local/rpms/bash#5f22bafc903fd0343640a6d7e25c87e32e504b9c'
    bash_internal_source = SourceLocation(url=bash_internal_url).save()
    bash_build.source_location.connect(bash_internal_source)
    bash_internal_source.upstream.connect(bash_upstream_source)
    bash_component = Component(canonical_type='generic', canonical_namespace='',
                               canonical_name='bash').save()
    bash_internal_source.component.connect(bash_component)
    bash_upstream_source.component.connect(bash_component)

    # Parent image
    parent_build = Build(id_='2000', type_='container').save()
    parent_filename = 'docker-image-sha256:' + '0' * 64 + '.x86_64.tar.gz'
    parent = Artifact(
        archive_id='2001',
        architecture='x86_64',
        filename=parent_filename,
        type_='container').save()
    parent_build.artifacts.connect(parent)
    container_internal_url = 'git://pkgs.domain.local/containers/parent#...'
    container_internal_source = SourceLocation(url=container_internal_url).save()
    parent_build.source_location.connect(container_internal_source)
    parent.embedded_artifacts.connect(bash_rpm)  # bash RPM is installed

    # etcd RPM for container image we'll query
    etcd_build = Build(id_='3000', type_='rpm').save()
    etcd_rpm = Artifact(
        archive_id='3001',
        architecture='x86_64',
        filename='etcd-3.2.22-1.el7.x86_64.rpm',
        type_='rpm').save()
    etcd_build.artifacts.connect(etcd_rpm)

    # Add an additional architecture that is not used by the build
    # we'll query about. This is to test we are not selecting
    # artifacts we should not be.
    etcd_unused_rpm = Artifact(
        archive_id='3002',
        architecture='ppc64le',
        filename='etcd-3.2.22-1.el7.ppc64le.rpm',
        type_='rpm').save()
    etcd_build.artifacts.connect(etcd_unused_rpm)

    # Sources for etcd
    etcd_upstream_url = ('https://github.com/coreos/etcd/archive/'
                         '1674e682fe9fbecd66e9f20b77da852ad7f517a9/etcd-1674e68.tar.gz')
    etcd_upstream_source = SourceLocation(url=etcd_upstream_url,
                                          canonical_version='3.2.22').save()
    etcd_internal_url = 'git://pkgs.domain.local/rpms/etcd#84858fb38a89e1177b0303c675d206f90f6a83e2'
    etcd_internal_source = SourceLocation(url=etcd_internal_url).save()
    etcd_build.source_location.connect(etcd_internal_source)
    etcd_internal_source.upstream.connect(etcd_upstream_source)
    etcd_component = Component(canonical_type='github', canonical_namespace='coreos',
                               canonical_name='etcd').save()
    etcd_internal_source.component.connect(etcd_component)
    etcd_upstream_source.component.connect(etcd_component)

    # The container itself
    container_build = Build(id_='4000', type_='container').save()
    container_filename = 'docker-image-sha256:' + '1' * 64 + '.x86_64.tar.gz'
    image = Artifact(
        archive_id='4001',
        architecture='x86_64',
        filename=container_filename,
        type_='container').save()
    container_build.artifacts.connect(image)
    container_internal_url = ('git://pkgs.domain.local/containers/image#...')
    container_internal_source = SourceLocation(url=container_internal_url).save()
    container_build.source_location.connect(container_internal_source)
    image.embedded_artifacts.connect(parent)  # inherits from parent image
    image.embedded_artifacts.connect(etcd_rpm)  # etcd RPM is installed

    # Go executable
    # Based on output from backvendor:
    # *github.com/jimmidyson/configmap-reload@043045da[...] =v0.2.2 ~v0.2.2
    # golang.org/x/sys@9c60d1c[...] ~v0.0.0-0.20150901164945-9c60d1c508f5
    # gopkg.in/fsnotify.v1@c282820[...] =v1.4.7 ~v1.4.7
    configmap_reload = SourceLocation(url='https://github.com/jimmidyson/configmap-reload',
                                      canonical_version='v0.2.2').save()
    configmap_reload_component = Component(
        canonical_type='golang',
        canonical_namespace='github.com/jimmidyson',
        canonical_name='configmap-reload').save()
    configmap_reload.component.connect(configmap_reload_component)
    x_sys = SourceLocation(url='https://go.googlesource.com/sys',
                           canonical_version='v0.0.0-0.20150901164945-9c60d1c508f5').save()
    x_sys.component.connect(
        Component(canonical_type='golang',
                  canonical_namespace='golang.org/x',
                  canonical_name='sys').save())
    fsnotify = SourceLocation(url='https://gopkg.in/fsnotify.v1',
                              canonical_version='v1.4.7').save()
    fsnotify.component.connect(
        Component(canonical_type='golang',
                  canonical_namespace='gopkg.in',
                  canonical_name='fsnotify.v1').save())

    container_internal_source.upstream.connect(configmap_reload)
    container_internal_source.component.connect(configmap_reload_component)
    container_internal_source.embedded_source_locations.connect(x_sys)
    container_internal_source.embedded_source_locations.connect(fsnotify)

    expected = {
        ('container', '4001'): {
            'artifact': {
                'architecture': 'x86_64',
                'filename': container_filename,
            },
            'embeds': {
                ('container', '2001'): {
                    'artifact': {
                        'architecture': 'x86_64',
                        'filename': parent_filename,
                    },
                    'embeds': {
                        ('rpm', '1001'): {
                            'artifact': {
                                'architecture': 'x86_64',
                                'filename': 'bash-4.2.46-30.el7.x86_64.rpm',
                            },
                            'sources': [
                                {
                                    'name': 'bash',
                                    'namespace': '',
                                    'qualifiers': {'download_url': bash_upstream_url},
                                    'type': 'generic',
                                    'version': '4.2.46',
                                },
                            ],
                        },
                    },
                },
                ('rpm', '3001'): {
                    'artifact': {
                        'architecture': 'x86_64',
                        'filename': 'etcd-3.2.22-1.el7.x86_64.rpm',
                    },
                    'sources': [
                        {
                            'name': 'etcd',
                            'namespace': 'coreos',
                            'qualifiers': {'download_url': etcd_upstream_url},
                            'type': 'github',
                            'version': '3.2.22',
                        },
                    ],
                },
            },
            'sources': [
                {
                    'name': 'configmap-reload',
                    'namespace': 'github.com/jimmidyson',
                    'qualifiers': {
                        'download_url': 'https://github.com/jimmidyson/configmap-reload',
                    },
                    'type': 'golang',
                    'version': 'v0.2.2',
                },
                {
                    'name': 'sys',
                    'namespace': 'golang.org/x',
                    'qualifiers': {
                        'download_url': 'https://go.googlesource.com/sys',
                    },
                    'type': 'golang',
                    'version': 'v0.0.0-0.20150901164945-9c60d1c508f5',
                },
                {
                    'name': 'fsnotify.v1',
                    'namespace': 'gopkg.in',
                    'qualifiers': {
                        'download_url': 'https://gopkg.in/fsnotify.v1',
                    },
                    'type': 'golang',
                    'version': 'v1.4.7',
                },
            ],
        },
    }

    assert query.get_source_components_for_build('4000') == expected
