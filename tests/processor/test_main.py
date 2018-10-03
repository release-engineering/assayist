# SPDX-License-Identifier: GPL-3.0+

import mock
import pytest

from assayist.processor import base, main_analyzer
from assayist.common.models.content import Artifact, Build

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
          'extra': {'image': {'arch': 'x86_64'}}}

IMAGE2 = {'id': '2',
          'checksum': '89506da3abd1de6a00c8d1403b3259e5',
          'filename': 'image2.tar.gz',
          'buildroot_id': '2',
          'btype': 'image',
          'type': 'tar',
          'extra': {'image': {'arch': 'ppc64le'}}}

JAR = {'id': '3',
       'checksum': '89506da3abd1de6a00c8d1403b3259e6',
       'filename': 'camel-jmx-starter-2.18.1.redhat-000032.jar',
       'buildroot_id': None,
       'btype': 'maven',
       'type': 'jar',
       'extra': None}


SOURCE_URL = "git://example.com/containers/virt-api#e9614e8eed02befd8ed021fe9591f8453422"


# Test the basic function of the get_or_create methods
def test_get_or_create_build():
    """Test the basic function of get_or_create_build."""
    analyzer = main_analyzer.MainAnalyzer()
    build = analyzer.get_or_create_build('1', 'type1')
    assert build.id_ == '1'
    assert build.type == 'type1'
    build.id  # exists, meaning it's been saved

    build2 = analyzer.get_or_create_build('1', 'type2')
    # this should be the same object as from the first call since id_ is the unique key
    assert build.id == build2.id

    # should be the same object if we query for it too
    assert Build.nodes.get_or_none(id_='1').id == build.id


def test_get_or_create_rpm_artifact():
    """Test the basic function of the get_or_create_rpm_artifact function."""
    analyzer = main_analyzer.MainAnalyzer()
    artifact = analyzer.get_or_create_rpm_artifact(
        id=VIM_1_2_3['id'],
        name=VIM_1_2_3['name'],
        version=VIM_1_2_3['version'],
        release=VIM_1_2_3['release'],
        arch=VIM_1_2_3['arch'],
        checksum=VIM_1_2_3['payloadhash'])

    assert 'vim-2-3.el7.x86_64.rpm' == artifact.filename
    assert VIM_1_2_3['id'] == artifact.archive_id
    assert VIM_1_2_3['arch'] == artifact.architecture
    assert 'rpm' == artifact.type
    assert VIM_1_2_3['payloadhash'] == artifact.checksums[0].checksum
    assert 'md5' == artifact.checksums[0].algorithm
    assert 'unsigned' == artifact.checksums[0].checksum_source
    artifact.id  # exists, hence is saved

    # 're-creating' should just return existing node
    artifact2 = analyzer.get_or_create_rpm_artifact(
        id=VIM_1_2_3['id'],
        name=VIM_1_2_3['name'],
        version=VIM_1_2_3['version'],
        release=VIM_1_2_3['release'],
        arch=VIM_1_2_3['arch'],
        checksum=VIM_1_2_3['payloadhash'])
    assert artifact.id == artifact2.id


def test_get_or_create_rpm_artifact_from_rpm_info():
    """Test the basic function of the get_or_create_rpm_artifact_from_rpm_info function."""
    analyzer = main_analyzer.MainAnalyzer()
    artifact = analyzer.get_or_create_rpm_artifact_from_rpm_info(VIM_1_2_3)

    assert 'vim-2-3.el7.x86_64.rpm' == artifact.filename
    assert VIM_1_2_3['id'] == artifact.archive_id
    assert VIM_1_2_3['arch'] == artifact.architecture
    assert 'rpm' == artifact.type
    assert VIM_1_2_3['payloadhash'] == artifact.checksums[0].checksum
    assert 'md5' == artifact.checksums[0].algorithm
    assert 'unsigned' == artifact.checksums[0].checksum_source
    artifact.id  # exists, hence is saved

    # 're-creating' should just return existing node
    artifact2 = analyzer.get_or_create_rpm_artifact_from_rpm_info(VIM_1_2_3)
    assert artifact.id == artifact2.id


def test_get_or_create_container_archive_artifact():
    """Test the basic function of the get_or_create_archive_artifact function with a container."""
    analyzer = main_analyzer.MainAnalyzer()
    arch = 'x86_64'
    artifact = analyzer.get_or_create_archive_artifact(
        archive_id=IMAGE1['id'],
        filename=IMAGE1['filename'],
        arch=arch,
        type=IMAGE1['btype'],
        checksum=IMAGE1['checksum'])

    assert IMAGE1['filename'] == artifact.filename
    assert IMAGE1['id'] == artifact.archive_id
    assert arch == artifact.architecture
    assert 'container' == artifact.type
    assert IMAGE1['checksum'] == artifact.checksums[0].checksum
    assert 'md5' == artifact.checksums[0].algorithm
    assert 'unsigned' == artifact.checksums[0].checksum_source
    artifact.id  # exists, hence is saved

    # 're-creating' should just return existing node
    artifact2 = analyzer.get_or_create_archive_artifact(
        archive_id=IMAGE1['id'],
        filename=IMAGE1['filename'],
        arch=arch,
        type=IMAGE1['btype'],
        checksum=IMAGE1['checksum'])
    assert artifact.id == artifact2.id


def test_get_or_create_maven_archive_artifact():
    """Test the basic function of the get_or_create_archive_artifact with a maven artifact."""
    analyzer = main_analyzer.MainAnalyzer()
    arch = 'x86_64'
    artifact = analyzer.get_or_create_archive_artifact(
        archive_id=JAR['id'],
        filename=JAR['filename'],
        arch=arch,
        type=JAR['btype'],
        checksum=JAR['checksum'])

    assert JAR['filename'] == artifact.filename
    assert JAR['id'] == artifact.archive_id
    assert arch == artifact.architecture
    assert 'maven' == artifact.type
    assert JAR['checksum'] == artifact.checksums[0].checksum
    assert 'md5' == artifact.checksums[0].algorithm
    assert 'unsigned' == artifact.checksums[0].checksum_source
    artifact.id  # exists, hence is saved

    # 're-creating' should just return existing node
    artifact2 = analyzer.get_or_create_archive_artifact(
        archive_id=JAR['id'],
        filename=JAR['filename'],
        arch=arch,
        type=JAR['btype'],
        checksum=JAR['checksum'])
    assert artifact.id == artifact2.id


def test_get_or_create_source_location():
    """Test the basic function of the get_or_create_source_location function."""
    analyzer = main_analyzer.MainAnalyzer()
    url = 'www.whatever.com'
    canonical_version = 'pi'
    sl = analyzer.get_or_create_source_location(
        url=url,
        canonical_version=canonical_version)

    assert sl.url == url
    assert sl.canonical_version == sl.canonical_version
    sl.id  # exists, hence is saved

    # 're-creating' should just return existing node
    sl2 = analyzer.get_or_create_source_location(
        url=url,
        canonical_version=canonical_version)
    assert sl.id == sl2.id


def test_get_or_create_component():
    """Test the basic function of the get_or_create_component function."""
    analyzer = main_analyzer.MainAnalyzer()
    namespace = 'Pizza Hut'
    name = 'Pepperoni'
    type = 'pizza'
    component = analyzer.get_or_create_component(
        canonical_namespace=namespace,
        canonical_name=name,
        canonical_type=type)

    assert component.canonical_namespace == namespace
    assert component.canonical_name == name
    assert component.canonical_type == type
    component.id  # exists, hence is saved

    # 're-creating' should just return existing node
    component2 = analyzer.get_or_create_component(
        canonical_namespace=namespace,
        canonical_name=name,
        canonical_type=type)
    assert component.id == component2.id


def good_run(self):
    """Mock a simple run and succeed."""
    self.get_or_create_build('1234', '1')


@mock.patch('assayist.processor.main_analyzer.MainAnalyzer.run', new=good_run)
def test_main_good():
    """Ensure that the main function normally runs and commits successfully."""
    analyzer = main_analyzer.MainAnalyzer()
    analyzer.main()
    # should have been successfully created
    assert Build.nodes.get(id_='1234')


def bad_run(self):
    """Mock a simple run and throw an exception."""
    self.get_or_create_build('4321', '2')
    raise ValueError()


@mock.patch('assayist.processor.main_analyzer.MainAnalyzer.run', new=bad_run)
def test_main_bad():
    """Ensure that the main function rolls back in the case of an error."""
    analyzer = main_analyzer.MainAnalyzer()
    with pytest.raises(ValueError):
        analyzer.main()

    assert not Build.nodes.get_or_none(id_='4321')  # should have been rolled back


def test__construct_and_save_component():
    """Test the basic functioning of the _construct_and_save_component method."""
    analyzer = main_analyzer.MainAnalyzer()
    btype = 'build'  # rpm build
    binfo = {
        'name': 'kernel',
        'version': '123',
        'release': '4.el7'}
    component, version = analyzer._construct_and_save_component(btype, binfo)
    assert version == '123-4.el7'
    assert component.canonical_namespace == 'redhat'
    assert component.canonical_name == 'kernel'
    assert component.canonical_type == 'rpm'
    component.id  # exists, hence is saved

    btype = 'maven'
    binfo = {
        'name': 'com.redhat.fuse.eap-fuse-eap',
        'version': '6.3.0.redhat_356',
        'release': '1'}
    component, version = analyzer._construct_and_save_component(btype, binfo)
    assert version == '6.3.0.redhat-356'
    assert component.canonical_namespace == 'com.redhat.fuse.eap'
    assert component.canonical_name == 'fuse-eap'
    assert component.canonical_type == 'java'
    component.id  # exists, hence is saved

    btype = 'buildContainer'
    binfo = {
        'name': 'virt-api-container',
        'version': '1.2',
        'release': '4'}
    component, version = analyzer._construct_and_save_component(btype, binfo)
    assert version == '1.2-4'
    assert component.canonical_namespace == 'docker-image'
    assert component.canonical_name == 'virt-api-container'
    assert component.canonical_type == 'image'
    component.id  # exists, hence is saved


def read_metadata_test_data(self, FILE):
    """Mock out this function so we can use test data."""
    if FILE == base.Analyzer.MESSAGE_FILE:
        return {'info': {'build_id': 759153}}
    if FILE == base.Analyzer.BUILD_FILE:
        return {'id': 759153,
                'source': SOURCE_URL,
                'name': 'virt-api-container',
                'version': '1.2',
                'release': '4'}
    if FILE == base.Analyzer.TASK_FILE:
        return {'method': 'buildContainer'}
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
def test__read_and_save_buildroots():
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
    assert source.component[0].canonical_type == 'image'

    # assert the embedded artifacts are linked (rpms contained inside an image)
    image1 = Artifact.nodes.get(filename=IMAGE1['filename'])
    image2 = Artifact.nodes.get(filename=IMAGE2['filename'])
    assert len(image1.embedded_artifacts) == 1
    assert image1.embedded_artifacts[0].checksums[0].checksum == NETWORKMANAGER_5_6_7_X86[
        'payloadhash']
    assert len(image2.embedded_artifacts) == 1
    assert image2.embedded_artifacts[0].checksums[0].checksum == NETWORKMANAGER_5_6_7_PPC[
        'payloadhash']
    assert len(vim.embedded_artifacts) == 0
    assert len(ssh.embedded_artifacts) == 0
    assert len(jar.embedded_artifacts) == 0
