# SPDX-License-Identifier: GPL-3.0+

from assayist.client import query
from assayist.common.models.content import Artifact, Build
from assayist.common.models.source import SourceLocation, Component
from tests.factories import UseCaseFactory


def test_get_container_sources():
    """Test the get_container_sources function."""
    container_build_id, internal_urls, upstream_urls = UseCaseFactory.container_with_rpm_artifacts()
    expected = {
        'internal_urls': internal_urls,
        'upstream_urls': upstream_urls,
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


def test_get_current_and_previous_versions():
    """Test the get_current_and_previous_versions function."""
    go = Component(
        canonical_name='golang', canonical_type='generic', canonical_namespace='redhat').save()
    next_sl = None
    url = 'git://pkgs.domain.local/rpms/golang?#fed96461b05c0078e537c93a3fe974e8b334{version}'
    for version in ('1.9.7', '1.9.6', '1.9.5', '1.9.4', '1.9.3'):
        sl = SourceLocation(
            url=url.format(version=version.replace('.', '')), canonical_version=version).save()
        sl.component.connect(go)
        if next_sl:
            next_sl.previous_version.connect(sl)
        next_sl = sl

    rv = query.get_current_and_previous_versions('golang', 'generic', '1.9.6')
    versions = set([result['canonical_version'] for result in rv])
    assert versions == set(['1.9.6', '1.9.5', '1.9.4', '1.9.3'])


def test_get_container_built_with_artifact():
    """
    Test the test_get_container_built_with_artifact function.

    This test data creates a scenario where there are container builds with vulnerable golang
    RPMs embedded, that are used during multi-stage builds. There is also a container with the
    prometheus RPM embedded, but the prometheus RPM was built with a vulnerable version of the
    golang RPMs.
    """
    expected = set()
    api_input = []
    queried_sl_versions = {'1.9.6', '1.9.5', '1.9.3'}
    go = Component(
        canonical_name='golang', canonical_type='generic', canonical_namespace='redhat').save()

    artifact_counter = 0
    build_counter = 0
    next_sl = None
    url = 'git://pkgs.domain.local/rpms/golang?#fed96461b05c0078e537c93a3fe974e8b334{version}'

    for version in ('1.9.7', '1.9.6', '1.9.5', '1.9.4', '1.9.3'):
        sl = SourceLocation(
            url=url.format(version=version.replace('.', '')), canonical_version=version).save()
        sl.component.connect(go)
        if next_sl:
            next_sl.previous_version.connect(sl)
        if version in queried_sl_versions:
            api_input.append({'url': sl.url})
        go_build = Build(id_=build_counter, type_='rpm').save()
        go_build.source_location.connect(sl)
        build_counter += 1

        go_src_rpm_artifact = Artifact(archive_id=artifact_counter, type_='rpm', architecture='src',
                                       filename=f'golang-{version}-1.el7.src.rpm').save()
        go_src_rpm_artifact.build.connect(go_build)
        artifact_counter += 1

        # Don't create container builds for version 1.9.3 because it'll be used by prometheus below
        # to test another part of the query
        if version != '1.9.3':
            go_container_build = Build(id_=build_counter, type_='container').save()
            build_counter += 1

            content_container_build = Build(id_=build_counter, type_='container').save()
            if version in queried_sl_versions:
                # All the content containers are built with a container with a vulnerable golang
                # RPM, but since we only query for certain source location versions of golang, only
                # add those we are searching for.
                expected.add(str(content_container_build.id_))
            build_counter += 1

        for noarch_rpm in ('docs', 'misc', 'src', 'tests'):
            go_noarch_artifact = Artifact(
                archive_id=artifact_counter, type_='rpm', architecture='noarch',
                filename=f'golang-{noarch_rpm}-{version}-1.el7.noarch.rpm').save()
            go_noarch_artifact.build.connect(go_build)
            artifact_counter += 1

        for arch in ('aarch64', 'x86_64', 'ppc64le', 's390x'):
            go_artifact = Artifact(archive_id=artifact_counter, type_='rpm', architecture=arch,
                                   filename=f'golang-{version}-1.el7.{arch}.rpm').save()
            go_artifact.build.connect(go_build)
            artifact_counter += 1
            gobin_artifact = Artifact(archive_id=artifact_counter, type_='rpm', architecture=arch,
                                      filename=f'golang-bin-{version}-1.el7.{arch}.rpm').save()
            gobin_artifact.build.connect(go_build)
            artifact_counter += 1

            if version != '1.9.3':
                go_container_build_artifact = Artifact(
                    archive_id=artifact_counter, type_='container', architecture=arch).save()
                go_container_build_artifact.build.connect(go_container_build)
                go_container_build_artifact.embedded_artifacts.connect(go_artifact)
                go_container_build_artifact.embedded_artifacts.connect(gobin_artifact)
                artifact_counter += 1

                content_container_artifact = Artifact(
                    archive_id=artifact_counter, type_='container', architecture=arch).save()
                content_container_artifact.build.connect(content_container_build)
                content_container_artifact.buildroot_artifacts.connect(go_container_build_artifact)
                artifact_counter += 1

        next_sl = sl

    prometheus = Component(
        canonical_name='prometheus', canonical_type='generic', canonical_namespace='redhat').save()
    prometheus_url = ('git://pkgs.domain.local/rpms/golang-github-prometheus-prometheus?#41d8a98364'
                      'a9c631c7f663bbda8942cb2741df49')
    prometheus_sl = SourceLocation(url=prometheus_url, canonical_version='2.1.0').save()
    prometheus_sl.component.connect(prometheus)
    prometheus_build = Build(id_=build_counter, type_='rpm').save()
    prometheus_build.source_location.connect(prometheus_sl)
    build_counter += 1
    prometheus_src_rpm_artifact = Artifact(
        archive_id=artifact_counter, type_='rpm', architecture='src',
        filename='golang-github-prometheus-prometheus-2.2.1-1.gitbc6058c.el7.src.rpm').save()
    prometheus_src_rpm_artifact.build.connect(go_build)
    artifact_counter += 1
    prometheus_container_build = Build(id_=build_counter, type_='container').save()
    # This prometheus container will embed a prometheus RPM that was built with a vulnerable golang
    # RPM, and 1.9.3 is part of the query
    expected.add(str(prometheus_container_build.id_))
    build_counter += 1

    for arch in ('x86_64', 's390x', 'ppc64le'):
        prometheus_artifact = Artifact(
            archive_id=artifact_counter, type_='rpm', architecture=arch,
            filename=f'prometheus-2.2.1-1.gitbc6058c.el7.{arch}.rpm').save()
        prometheus_artifact.build.connect(prometheus_build)
        # Set the 1.9.3 go artifacts to be buildroot artifacts
        go_artifact = Artifact.nodes.get(filename=f'golang-1.9.3-1.el7.{arch}.rpm')
        prometheus_artifact.buildroot_artifacts.connect(go_artifact)
        gobin_artifact = Artifact.nodes.get(filename=f'golang-bin-1.9.3-1.el7.{arch}.rpm')
        prometheus_artifact.buildroot_artifacts.connect(gobin_artifact)
        artifact_counter += 1
        prometheus_container_artifact = Artifact(
            archive_id=artifact_counter, type_='container', architecture=arch).save()
        prometheus_container_artifact.build.connect(prometheus_container_build)
        prometheus_container_artifact.embedded_artifacts.connect(prometheus_artifact)
        artifact_counter += 1

    rv = query.get_container_built_with_sources(api_input)

    assert set(rv) == expected
