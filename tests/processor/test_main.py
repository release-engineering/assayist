# SPDX-License-Identifier: GPL-3.0+

import random

import mock
import pytest

from assayist.processor import base, main_analyzer
from assayist.common.models.content import Artifact, Build
from assayist.common.models.source import Component, SourceLocation

# RPM INFO BLOBS
VIM_1_2_3 = {'buildroot_id': '1',
             'id': '1',
             'name': 'vim',
             'epoch': '1',
             'version': '2',
             'release': '3.el7',
             'arch': 'x86_64',
             'payloadhash': '89506da3abd1de6a00c8d1403b3259d7'}

VIM_2_3 = {'buildroot_id': '1',
           'id': '2',
           'name': 'vim',
           'epoch': None,
           'version': '2',
           'release': '3.el7',
           'arch': 'x86_64',
           'payloadhash': '89506da3abd1de6a00c8d1403b3259d8'}

SSH_9_8_7 = {'buildroot_id': '2',
             'id': '3',
             'name': 'ssh',
             'epoch': '9',
             'version': '8',
             'release': '7.el7',
             'arch': 'x86_64',
             'payloadhash': '89506da3abd1de6a00c8d1403b3259d9'}

NETWORKMANAGER_5_6_7_X86 = {'id': '4',
                            'name': 'NetworkManager',
                            'epoch': '5',
                            'version': '6',
                            'release': '7.el7',
                            'arch': 'x86_64',
                            'payloadhash': '89506da3abd1de6a00c8d1403b3259e0'}

NETWORKMANAGER_5_6_7_PPC = {'id': '5',
                            'name': 'NetworkManager',
                            'epoch': '5',
                            'version': '6',
                            'release': '7.el7',
                            'arch': 'ppc64le',
                            'payloadhash': '89506da3abd1de6a00c8d1403b3259e1'}

GCC_2_3_4 = {'id': '6',
             'name': 'gcc',
             'epoch': '2',
             'version': '3',
             'release': '4.el7',
             'arch': 'x86_64',
             'payloadhash': '89506da3abd1de6a00c8d1403b3259e2'}

PYTHON_3_6_7 = {'id': '7',
                'name': 'python',
                'epoch': '3',
                'version': '6',
                'release': '7.el7',
                'arch': 'x86_64',
                'payloadhash': '89506da3abd1de6a00c8d1403b3259e3'}

# ARCHIVE BLOBS
IMAGE1 = {'id': '1',
          'checksum': '89506da3abd1de6a00c8d1403b3259e4',
          'filename': 'image1.tar.gz',
          'buildroot_id': '1',
          'btype': 'image',
          'type': 'tar',
          'version': '6',
          'release': '7.el7',
          'extra': {
              'image': {
                  'arch': 'x86_64',
                  'index': {
                      'pull': [
                          'repo.example.com/openshift/example-project@sha256:deadbeef',
                          'repo.example.com/openshift/example-project:123-4321']}}}}

IMAGE2 = {'id': '2',
          'checksum': '89506da3abd1de6a00c8d1403b3259e5',
          'filename': 'image2.tar.gz',
          'buildroot_id': '2',
          'btype': 'image',
          'type': 'tar',
          'version': '6',
          'release': '7.el7',
          'extra': {
              'image': {
                  'arch': 'ppc64le',
                  'index': {
                      'pull': [
                          'repo.example.com/openshift/example-project@sha256:deadbeef',
                          'repo.example.com/openshift/example-project:123-4321']}}}}

JAR = {'id': '3',
       'checksum': '89506da3abd1de6a00c8d1403b3259e6',
       'filename': 'camel-jmx-starter-2.18.1.redhat-000032.jar',
       'buildroot_id': None,
       'btype': 'maven',
       'type': 'jar',
       'extra': None}


SOURCE_URL = "git://example.com/containers/virt-api#e9614e8eed02befd8ed021fe9591f8453422"


def test_create_or_update_rpm_artifact():
    """Test the basic function of the create_or_update_rpm_artifact function."""
    analyzer = main_analyzer.MainAnalyzer()
    artifact = analyzer.create_or_update_rpm_artifact(
        rpm_id=VIM_1_2_3['id'],
        name=VIM_1_2_3['name'],
        version=VIM_1_2_3['version'],
        release=VIM_1_2_3['release'],
        arch=VIM_1_2_3['arch'],
        checksum=VIM_1_2_3['payloadhash'])

    assert 'vim-2-3.el7.x86_64.rpm' == artifact.filename
    assert VIM_1_2_3['id'] == artifact.archive_id
    assert VIM_1_2_3['arch'] == artifact.architecture
    assert 'rpm' == artifact.type_
    assert VIM_1_2_3['payloadhash'] == artifact.checksums[0].checksum
    assert 'md5' == artifact.checksums[0].algorithm
    assert 'unsigned' == artifact.checksums[0].checksum_source
    artifact.id  # exists, hence is saved

    # 're-creating' should just return existing node
    artifact2 = analyzer.create_or_update_rpm_artifact(
        rpm_id=VIM_1_2_3['id'],
        name=VIM_1_2_3['name'],
        version=VIM_1_2_3['version'],
        release=VIM_1_2_3['release'],
        arch=VIM_1_2_3['arch'],
        checksum=VIM_1_2_3['payloadhash'])
    assert artifact.id == artifact2.id


def test_create_or_update_rpm_artifact_from_rpm_info():
    """Test the basic function of the create_or_update_rpm_artifact_from_rpm_info function."""
    analyzer = main_analyzer.MainAnalyzer()
    artifact = analyzer.create_or_update_rpm_artifact_from_rpm_info(VIM_1_2_3)

    assert 'vim-2-3.el7.x86_64.rpm' == artifact.filename
    assert VIM_1_2_3['id'] == artifact.archive_id
    assert VIM_1_2_3['arch'] == artifact.architecture
    assert 'rpm' == artifact.type_
    assert VIM_1_2_3['payloadhash'] == artifact.checksums[0].checksum
    assert 'md5' == artifact.checksums[0].algorithm
    assert 'unsigned' == artifact.checksums[0].checksum_source
    artifact.id  # exists, hence is saved

    # 're-creating' should just return existing node
    artifact2 = analyzer.create_or_update_rpm_artifact_from_rpm_info(VIM_1_2_3)
    assert artifact.id == artifact2.id


def test_create_or_update_container_archive_artifact():
    """Test the basic function of the create_or_update_archive_artifact function for a container."""
    analyzer = main_analyzer.MainAnalyzer()
    arch = 'x86_64'
    artifact = analyzer.create_or_update_archive_artifact(
        archive_id=IMAGE1['id'],
        filename=IMAGE1['filename'],
        arch=arch,
        archive_type=IMAGE1['btype'],
        checksum=IMAGE1['checksum'])

    assert IMAGE1['filename'] == artifact.filename
    assert IMAGE1['id'] == artifact.archive_id
    assert arch == artifact.architecture
    assert 'container' == artifact.type_
    assert IMAGE1['checksum'] == artifact.checksums[0].checksum
    assert 'md5' == artifact.checksums[0].algorithm
    assert 'unsigned' == artifact.checksums[0].checksum_source
    artifact.id  # exists, hence is saved

    # 're-creating' should just return existing node
    artifact2 = analyzer.create_or_update_archive_artifact(
        archive_id=IMAGE1['id'],
        filename=IMAGE1['filename'],
        arch=arch,
        archive_type=IMAGE1['btype'],
        checksum=IMAGE1['checksum'])
    assert artifact.id == artifact2.id


@pytest.mark.parametrize('image', [IMAGE1, IMAGE2])
def test_create_or_update_container_archive_artifact_from_archive_info(image):
    """Test the create_or_update_archive_artifact_from_archive_info function for a container."""
    analyzer = main_analyzer.MainAnalyzer()
    artifact = analyzer.create_or_update_archive_artifact_from_archive_info(image)

    assert image['filename'] == artifact.filename
    assert image['id'] == artifact.archive_id
    assert image['extra']['image']['arch'] == artifact.architecture
    assert 'container' == artifact.type_
    assert image['checksum'] == artifact.checksums[0].checksum
    assert 'md5' == artifact.checksums[0].algorithm
    assert 'unsigned' == artifact.checksums[0].checksum_source
    assert hasattr(artifact, 'id')  # ID exists, hence is saved

    artifact2 = analyzer.create_or_update_archive_artifact_from_archive_info(image)
    assert artifact.id == artifact2.id


def test_create_or_update_maven_archive_artifact():
    """Test the basic function of the create_or_update_archive_artifact with a maven artifact."""
    analyzer = main_analyzer.MainAnalyzer()
    arch = 'x86_64'
    artifact = analyzer.create_or_update_archive_artifact(
        archive_id=JAR['id'],
        filename=JAR['filename'],
        arch=arch,
        archive_type=JAR['btype'],
        checksum=JAR['checksum'])

    assert JAR['filename'] == artifact.filename
    assert JAR['id'] == artifact.archive_id
    assert arch == artifact.architecture
    assert 'maven' == artifact.type_
    assert JAR['checksum'] == artifact.checksums[0].checksum
    assert 'md5' == artifact.checksums[0].algorithm
    assert 'unsigned' == artifact.checksums[0].checksum_source
    artifact.id  # exists, hence is saved

    # 're-creating' should just return existing node
    artifact2 = analyzer.create_or_update_archive_artifact(
        archive_id=JAR['id'],
        filename=JAR['filename'],
        arch=arch,
        archive_type=JAR['btype'],
        checksum=JAR['checksum'])
    assert artifact.id == artifact2.id


def test_create_or_update_maven_archive_artifact_from_artifact_info():
    """Test the create_or_update_archive_artifact_from_archive_info function on a maven artifact."""
    analyzer = main_analyzer.MainAnalyzer()
    artifact = analyzer.create_or_update_archive_artifact_from_archive_info(JAR)

    assert JAR['filename'] == artifact.filename
    assert JAR['id'] == artifact.archive_id
    assert 'noarch' == artifact.architecture
    assert 'maven' == artifact.type_
    assert JAR['checksum'] == artifact.checksums[0].checksum
    assert 'md5' == artifact.checksums[0].algorithm
    assert 'unsigned' == artifact.checksums[0].checksum_source
    assert hasattr(artifact, 'id')  # ID exists, hence is saved

    # 're-creating' should just return existing node
    artifact2 = analyzer.create_or_update_archive_artifact_from_archive_info(JAR)
    assert artifact.id == artifact2.id


def test_create_or_update_source_location():
    """Test the basic function of the create_or_update_source_location function."""
    rpm_comp = Component.get_or_create_singleton('a', 'test', 'rpm')
    analyzer = main_analyzer.MainAnalyzer()
    url = 'www.whatever.com'
    canonical_version = '0-1-2'
    sl = analyzer.create_or_update_source_location(
        url=url,
        component=rpm_comp,
        canonical_version=canonical_version)

    assert sl.url == url
    assert sl.canonical_version == sl.canonical_version
    assert sl.type_ == 'upstream'
    assert rpm_comp in sl.component
    sl.id  # exists, hence is saved

    # 're-creating' should just return existing node
    sl2 = analyzer.create_or_update_source_location(
        url=url,
        component=rpm_comp,
        canonical_version=canonical_version)
    assert sl.id == sl2.id


@mock.patch('assayist.processor.base.Analyzer.conditional_connect')
def test_create_or_update_source_location_bad(m_conditional_connect):
    """Test that create_or_update_source_location rolls back on error."""
    m_conditional_connect.side_effect = ValueError('something broke')

    rpm_comp = Component.get_or_create_singleton('a', 'test', 'rpm')
    analyzer = main_analyzer.MainAnalyzer()
    url = 'www.whatever.com'
    canonical_version = '0-1-3'

    raised = False
    try:
        analyzer.create_or_update_source_location(
            url=url,
            component=rpm_comp,
            canonical_version=canonical_version)
    except ValueError:
        raised = True

    assert raised
    sl = SourceLocation.nodes.get_or_none(url=url, type_='upstream')
    assert not sl


def test_supersedes_order_rpm():
    """Test that RPM SourceLocations are associated in the correct order."""
    rpm_comp = Component.get_or_create_singleton('another', 'test', 'rpm')

    URL_BASE = 'www.example.com/some/package#'
    analyzer = main_analyzer.MainAnalyzer()

    def get_sl(version):
        return analyzer.create_or_update_source_location(
            url=URL_BASE + str(random.randint(0, 10000)),
            component=rpm_comp,
            canonical_version=version)

    # named for what order they should come in, created in a random order
    fourth = get_sl('1-1.1-1.el7')
    fifth = get_sl('1-1.1a-1.el7')
    third = get_sl('0-3-1.el7')
    first = get_sl('0-2-2.el7')
    second = get_sl('0-2.1-1.el7')

    assert first.previous_version.single() is None
    assert second == first.next_version.single()
    assert third == second.next_version.single()
    assert fifth == fourth.next_version.single()
    assert fifth.next_version.single() is None


def test_supersedes_order_maven():
    """Test that Maven SourceLocations are associated in the correct order."""
    rpm_comp = Component.get_or_create_singleton('a', 'test', 'java')

    URL_BASE = 'www.example.com/some/package#'
    analyzer = main_analyzer.MainAnalyzer()

    def get_sl(version):
        return analyzer.create_or_update_source_location(
            url=URL_BASE + str(random.randint(0, 10000)),
            component=rpm_comp,
            canonical_version=version)

    # named for what order they should come in, created in a random order
    fourth = get_sl('7.1.0.fuse-710017-redhat-00002')
    fifth = get_sl('7.1.0.fuse-710018-redhat-00001')
    third = get_sl('7.1.0.fuse-710017-redhat-00001')
    first = get_sl('6.2.1.redhat-222')
    second = get_sl('6.3.0.redhat-356')

    assert first.previous_version.single() is None
    assert second == first.next_version.single()
    assert third == second.next_version.single()
    assert fifth == fourth.next_version.single()
    assert fifth.next_version.single() is None


def test_supersedes_order_container():
    """Test that conatiner SourceLocations are associated in the correct order."""
    rpm_comp = Component.get_or_create_singleton('a', 'test', 'docker')

    URL_BASE = 'www.example.com/some/package#'
    analyzer = main_analyzer.MainAnalyzer()

    def get_sl(version):
        return analyzer.create_or_update_source_location(
            url=URL_BASE + str(random.randint(0, 10000)),
            component=rpm_comp,
            canonical_version=version)

    # named for what order they should come in, created in a random order
    fourth = get_sl('v4.0.0-0.27.0.0')
    fifth = get_sl('v4.0.0-0.27.0.1')
    third = get_sl('v3.11.45-7')
    first = get_sl('v3.10.16-4')
    second = get_sl('v3.10.45-7')

    assert first.previous_version.single() is None
    assert second == first.next_version.single()
    assert third == second.next_version.single()
    assert fifth == fourth.next_version.single()
    assert fifth.next_version.single() is None


def good_run(self):
    """Mock a simple run and succeed."""
    Build.get_or_create({
        'id_': '1234',
        'type_': '1'})


@mock.patch('assayist.processor.main_analyzer.MainAnalyzer.run', new=good_run)
def test_main():
    """Ensure that the main function normally runs successfully."""
    analyzer = main_analyzer.MainAnalyzer()
    analyzer.main()
    # should have been successfully created
    assert Build.nodes.get(id_='1234')


def test_construct_and_save_component():
    """Test the basic functioning of the _construct_and_save_component method."""
    analyzer = main_analyzer.MainAnalyzer()
    btype = 'build'  # rpm build
    binfo = {
        'name': 'kernel',
        'version': '123',
        'release': '4.el7'}
    component, version = analyzer._construct_and_save_component(btype, binfo)
    assert version == '0-123-4.el7'
    assert component.canonical_namespace == 'redhat'
    assert component.canonical_name == 'kernel'
    assert component.canonical_type == 'rpm'
    component.id  # exists, hence is saved

    btype = 'maven'
    maven_info = {
        'group_id': 'com.redhat.fuse.eap',
        'artifact_id': 'fuse-eap',
        'version': '6.3.0.redhat_356'}
    with mock.patch.object(analyzer, 'read_metadata_file') as mocked_f:
        mocked_f.return_value = maven_info
        component, version = analyzer._construct_and_save_component(btype, binfo)
    assert version == '6.3.0.redhat_356'
    assert component.canonical_namespace == 'com.redhat.fuse.eap'
    assert component.canonical_name == 'fuse-eap'
    assert component.canonical_type == 'java'
    component.id  # exists, hence is saved

    btype = 'buildContainer'
    component, version = analyzer._construct_and_save_component(btype, IMAGE1)
    assert version == '6-7.el7'
    assert component.canonical_namespace == 'openshift'
    assert component.canonical_name == 'example-project'
    assert component.canonical_type == 'docker'
    component.id  # exists, hence is saved


def read_metadata_test_data(self, FILE):
    """Mock out this function so we can use test data."""
    if FILE == base.Analyzer.BUILD_FILE:
        return {
            'id': 759153,
            'source': SOURCE_URL,
            'name': 'virt-api-container',
            'version': '1.2',
            'release': '4',
            'type': 'buildContainer',
        }
    if FILE == base.Analyzer.TASK_FILE:
        return {'method': 'buildContainer'}
    if FILE == base.Analyzer.MAVEN_FILE:
        return {'group_id': 'com.example', 'artifact_id': 'maven', 'version': '1'}
    if FILE == base.Analyzer.RPM_FILE:
        return [VIM_1_2_3, SSH_9_8_7]
    if FILE == base.Analyzer.ARCHIVE_FILE:
        return [IMAGE1, IMAGE2, JAR]
    if FILE == base.Analyzer.IMAGE_RPM_FILE:
        return {'1': [NETWORKMANAGER_5_6_7_X86],
                '2': [NETWORKMANAGER_5_6_7_PPC]}
    if FILE == base.Analyzer.BUILDROOT_FILE:
        return {'1': [GCC_2_3_4],
                '2': [PYTHON_3_6_7]}
    raise Exception('Unexpected file being read, mock it out! %s', FILE)


@mock.patch('assayist.processor.base.Analyzer.read_metadata_file', new=read_metadata_test_data)
def test_read_and_save_buildroots():
    """
    Test the basic function of the _build_and_save_buildroots function.

    The links to other artifacts won't exist yet, but the buildroot artifacts themselves should
    exist.
    """
    analyzer = main_analyzer.MainAnalyzer()
    analyzer._read_and_save_buildroots()

    assert Artifact.nodes.get(filename='gcc-3-4.el7.x86_64.rpm')
    assert Artifact.nodes.get(filename='python-6-7.el7.x86_64.rpm')


@mock.patch('assayist.processor.base.Analyzer.read_metadata_file', new=read_metadata_test_data)
def test_run():
    """
    Test the general working of the main_analyzer.

    Ensure that the appropriate nodes and edges are created that we would expect from
    the read_metadata_test_data function.
    """
    # While this test reaches all aspects of the build analyzer it it somewhat unrealistic.
    # In reality a single build will not construct both rpms and maven artifact and images.
    analyzer = main_analyzer.MainAnalyzer()
    analyzer.run()
    # For an RPM build we expect:
    # * The rpm outputs to be linked
    # * The buildroot rpms to be linked
    # * The appropriate SourceLocation and Component to be created / linked

    # assert that the build artifacts are linked to the build correctly
    build = Build.nodes.get(id_='759153')
    assert len(build.artifacts) == 5
    vim = Artifact.nodes.get(filename='vim-2-3.el7.x86_64.rpm')
    ssh = Artifact.nodes.get(filename='ssh-8-7.el7.x86_64.rpm')
    image1 = Artifact.nodes.get(filename=IMAGE1['filename'])
    image2 = Artifact.nodes.get(filename=IMAGE2['filename'])
    jar = Artifact.nodes.get(filename=JAR['filename'])
    assert image1 in build.artifacts
    assert image2 in build.artifacts
    assert vim in build.artifacts
    assert ssh in build.artifacts
    assert jar in build.artifacts

    # assert that the buildroot rpms are linked to each artifact correctly
    assert len(vim.buildroot_artifacts) == 1
    assert 'gcc-3-4.el7.x86_64.rpm' == vim.buildroot_artifacts[0].filename
    assert len(ssh.buildroot_artifacts) == 1
    assert 'python-6-7.el7.x86_64.rpm' == ssh.buildroot_artifacts[0].filename
    assert len(image1.buildroot_artifacts) == 1
    assert 'gcc-3-4.el7.x86_64.rpm' == image1.buildroot_artifacts[0].filename
    assert len(image2.buildroot_artifacts) == 1
    assert 'python-6-7.el7.x86_64.rpm' == image2.buildroot_artifacts[0].filename
    assert len(jar.buildroot_artifacts) == 0

    # assert the sourcelocation is linked to the build
    assert len(build.source_location) == 1
    source = build.source_location[0]
    assert source.url == SOURCE_URL

    # assert the component is linked to the build
    assert source.component[0].canonical_name == 'virt-api-container'
    assert source.component[0].canonical_type == 'docker'

    assert len(vim.embedded_artifacts) == 0
    assert len(ssh.embedded_artifacts) == 0
    assert len(jar.embedded_artifacts) == 0


@pytest.mark.parametrize('input, expected_output', [
    ('koji-docker01.example.com:8989/rhel7-minimal@sha256:833101863e',
     ('', 'rhel7-minimal')),
    ('koji-docker01.example.com:8989/openshift3/ose-console@sha256:833101863e',
     ('openshift3', 'ose-console')),
    ('koji-docker01.example.com:8989/openshift3/ose-console/etcd@sha256:833101863e',
     ('openshift3/ose-console', 'etcd')),
])
def test_extract_component_name_and_namespace(input, expected_output):
    """Test the _extract_component_name_and_namespace() function."""
    analyzer = main_analyzer.MainAnalyzer()
    assert analyzer._extract_component_name_and_namespace(input) == expected_output


@mock.patch('assayist.processor.base.Analyzer.read_metadata_file')
def test_unsupported_build_type(m_read_metadata_file):
    """Test main Analyzer on unsupported build type."""
    m_read_metadata_file.return_value = {'id': 123, 'type': 'module'}  # Unsupported build type

    analyzer = main_analyzer.MainAnalyzer()
    analyzer.run()

    assert m_read_metadata_file.call_count == 1

    # Check that a Build node was created but nothing else
    build = Build.nodes.get(id_=123)
    assert build.type_ == 'module'
    assert len(build.artifacts) == 0
    assert len(build.source_location) == 0
