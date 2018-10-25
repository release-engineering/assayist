# SPDX-License-Identifier: GPL-3.0+

from collections.abc import Mapping, Collection

from assayist.client import query
from assayist.common.models.content import Build, Artifact
from assayist.common.models.source import SourceLocation, Component
from tests.factories import UseCaseFactory


def test_get_container_by_component():
    """Test the get_container_by_component function with a container that includes a component."""
    expected_build_id, _, _ = UseCaseFactory.container_with_rpm_artifacts()

    rv = query.get_container_by_component('yum-utils', 'generic', '1.1.31')
    assert rv == {int(expected_build_id)}


def test_get_container_with_maven_artifacts():
    """Test the get_container_by_component function with a container that embeds Maven artifacts."""
    expected_build_id = UseCaseFactory.container_with_maven_artifacts()

    rv = query.get_container_by_component('com.redhat.lightblue.client:lightblue-client-core',
                                          'maven', '10.0.1')
    assert rv == {int(expected_build_id)}


def test_get_container_by_embedded_component():
    """Test the get_container_by_component function with a container that embeds a component."""
    parent_build_id, build_id = UseCaseFactory.container_with_go_and_rpm_artifacts()

    assert query.get_container_by_component('fsnotify.v1', 'golang', 'v1.4.7') == {build_id}
    assert query.get_container_by_component('sys', 'golang',
                                            'v0.0.0-0.20150901164945-9c60d1c508f5') == {build_id}
    assert query.get_container_by_component('configmap-reload', 'golang', 'v0.2.2') == {build_id}
    assert query.get_container_by_component('bash', 'generic', '4.2.47') == {parent_build_id,
                                                                             build_id}


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

    _, build_id = UseCaseFactory.container_with_go_and_rpm_artifacts()
    result = query.get_source_components_for_build(build_id)

    def check_artifact_keys(d):
        """Check an artifact mapping's keys. They should be 2-tuples."""
        assert isinstance(d, Mapping)
        assert all(isinstance(key, tuple) for key in d)
        assert all(len(key) == 2 for key in d)

    # At the top level, the result should be a mapping whose keys are 2-tuples.
    check_artifact_keys(result)

    # There should be at least one artifact!
    assert result

    def check_structure(d):
        """Validate data structure."""
        for metadata in d.values():
            # Every 'artifact' should have 'architecture' and 'filename' keys
            artifact = metadata['artifact']
            for k in ('architecture', 'filename'):
                assert k in artifact and isinstance(artifact[k], str)

            # The 'sources' are optional
            if 'sources' in metadata:
                # Should be a list. (Right now they are a list of
                # mappings, but in future they should be a list of
                # strings.)
                assert isinstance(metadata['sources'], Collection)

            # The 'embeds' key is optional
            if 'embeds' in metadata:
                embeds = metadata['embeds']

                # Check structure recursively
                check_artifact_keys(embeds)
                check_structure(embeds)

    # Each top-level item should be an artifact for a different
    # architecture -- these are the artifacts produced by the build we
    # queried about.
    arches = [value['artifact']['architecture'] for value in result.values()]
    assert len(arches) == len(set(arches))

    # Each top-level item should be a container image
    assert all(objtype == 'container' for objtype, _ in result.keys())

    # Check the overall data structure.
    check_artifact_keys(result)

    def find_source(d, keyvals, path=()):
        """Return the path of object types leading to a given source name."""
        for key, metadata in d.items():
            objtype, _ = key
            for source in metadata.get('sources', []):
                # Compare the canonical name
                if all(source.get(key) == val for key, val in keyvals.items()):
                    return path + (objtype,)

            if 'embeds' in metadata:
                result = find_source(metadata['embeds'], keyvals,
                                     path + (objtype,))
                if result is not None:
                    return result

    # The build we queried about should directly have the source for
    # the Go packages it built from.
    for keyvals in (
            {
                'type': 'golang',
                'namespace': 'gopkg.in',
                'name': 'fsnotify.v1',
                'version': 'v1.4.7',
            },
            {
                'type': 'golang',
                'namespace': 'github.com/jimmidyson',
                'name': 'configmap-reload',
                'version': 'v0.2.2',
            },
            {
                'type': 'golang',
                'namespace': 'golang.org/x',
                'name': 'sys',
                'version': 'v0.0.0-0.20150901164945-9c60d1c508f5',
            },
    ):
        assert find_source(result, keyvals) == ('container',)

    # Etcd source comes via a container which embeds an rpm
    assert find_source(result, {
        'type': 'golang',
        'namespace': 'github.com/coreos',
        'name': 'etcd',
        'version': '3.2.22',
    }) == (
        'container',
        'rpm',
    )

    # Bash source comes via a container which embeds a container which
    # itself embeds an rpm
    assert find_source(result, {
        'type': 'generic',
        'name': 'bash',
        'version': '4.2.47',
    }) == (
        'container',
        'container',
        'rpm',
    )


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
