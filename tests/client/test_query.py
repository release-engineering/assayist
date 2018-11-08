# SPDX-License-Identifier: GPL-3.0+

from collections.abc import Mapping, Collection

from assayist.client import query
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
        'internal_urls': internal_urls[0:2],
        'upstream_urls': upstream_urls[0:2],
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
            url=url.format(version=version.replace('.', '')),
            canonical_version=version,
            type_='local').save()
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

    This test data creates two scenarios. In the first, there is a destination container called
    "app-xyz" that was built with the "python-builder-container". "python-builder-container" embeds
    a vulnerable "python-devel" RPM, therefore, the build ID of the "app-xyz" container should be
    part of the return value.

    In the second scenario, there is a container called "openshift-enterprise-base-container" which
    embeds the "yum-utils" RPM. This RPM was built with a vulnerable "python-devel" RPM, therefore,
    the build ID of the "openshift-enterprise-base-container" container should be part of the return
    value.

    The input to the API will be two internal source locations, each representing a different
    version of "python-devel".
    """
    traditional_cb_id, internal_sls, _ = UseCaseFactory.container_with_rpm_artifacts()
    python_devel_sl_url = internal_sls[2]
    _, _, _, multi_stage_builder = UseCaseFactory._container_build(
        'python-builder-container')
    _, _, app_container_build, app_container = UseCaseFactory._container_build(
        'app-xyz-container')
    _, python_devel_rpm, _, _, python_devel_sl2 = UseCaseFactory._rpm_build(
        'python-devel', '3.5.4')
    multi_stage_builder.embedded_artifacts.connect(python_devel_rpm)
    app_container.buildroot_artifacts.connect(multi_stage_builder)
    # This RPM doesn't affect the query, but it makes it so the "app-xyz" container at least has
    # some content to simulate the real world
    _, requests_rpm, _, _, _ = UseCaseFactory._rpm_build(
        'requests', '2.20.1', 'https://github.com/requests/requests/releases/tag/v2.20.1')
    app_container.embedded_artifacts.connect(requests_rpm)

    api_input = [
        {'url': python_devel_sl_url},
        {'url': python_devel_sl2.url}
    ]
    rv = query.get_container_built_with_sources(api_input)
    assert set(rv) == set([traditional_cb_id, app_container_build.id_])
