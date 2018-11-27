# SPDX-License-Identifier: GPL-3.0+

import os
import tempfile

import mock

from assayist.common.models import content
from assayist.processor.loose_artifact_analyzer import LooseArtifactAnalyzer
from tests.factories import BuildFactory, ArtifactFactory, ChecksumFactory

RPM_INFO = {
    'arch': 'noarch',
    'build_id': 484915,
    'epoch': None,
    'id': 4177917,
    'name': 'python-django',
    'payloadhash': '217ee68c509731aef889251cae1c4b10',
    'release': '1.el7ost',
    'version': '1.8.11',
}


def archive_info_generator(build_id, archive_id):
    """Generate a dict of info for an archive."""
    return {'build_id': build_id,
            'type_name': 'pom',
            'type_id': 3,
            'checksum': 'b8e892422c0e46cbe8b22d92e7c2517e',
            'extra': None,
            'filename': 'geronimo-osgi-registry-1.0.pom',
            'type_description': 'Maven Project Object Management file',
            'metadata_only': False,
            'type_extensions': 'pom',
            'btype': 'maven',
            'checksum_type': 0,
            'btype_id': 2,
            'buildroot_id': None,
            'id': archive_id,
            'size': 3320}


ARCHIVE_INFO1 = archive_info_generator(390981, 778931)
ARCHIVE_INFO2 = archive_info_generator(390982, 778932)
ARCHIVE_INFO3 = archive_info_generator(390983, 778933)
ARCHIVE_INFO4 = archive_info_generator(390984, 778934)
SOURCE_ARCHIVE_INFO = archive_info_generator(390985, 778935)


def create_test_file(test_dir, extension, content):
    """Touch files in the test directory."""
    x = os.path.join(test_dir, 'test_file.' + extension)
    with open(x, 'a') as f:
        f.write(content)
    return x


def test_unpacked_archives():
    """Test that the unpacked_archives method correctly finds all archives."""
    expected_paths = set()
    expected_archives = set()
    with tempfile.TemporaryDirectory() as temp_dir:
        def create_test_archive(a_type, name):
            path = os.path.join(temp_dir, 'unpacked_archives', a_type, name)
            os.makedirs(path)
            expected_paths.add(path)
            expected_archives.add(name)

        create_test_archive('rpm', 'name-1-2-3.noarch.rpm')
        create_test_archive('rpm', 'name2-1-2-3.noarch.rpm')
        create_test_archive('container_layer', 'docker-image:sha1234')
        create_test_archive('container_layer', 'docker-image:sha4321')
        create_test_archive('maven', 'really-important.jar')
        create_test_archive('maven', 'really-important-2.jar')

        analyzer = LooseArtifactAnalyzer(temp_dir)
        found_names = set()
        found_paths = set()
        for name, path in analyzer.unpacked_archives():
            found_names.add(name)
            found_paths.add(path)

        assert found_names == expected_archives
        assert found_paths == expected_paths


def test_files_to_examine():
    """Test the files_to_examine method correctly discoveres all files it's supposed to."""
    expected_files = set()
    with tempfile.TemporaryDirectory() as temp_dir:
        def create_test_archive(expected, *args):
            new_dir = os.path.join(temp_dir, *args[:-1])
            try:
                os.makedirs(new_dir)
            except FileExistsError:
                pass
            f = create_test_file(new_dir, args[-1], 'content')
            if expected:
                expected_files.add(f)

        create_test_archive(True, 'path', 'to', 'some', 'nested', 'thing.rpm')
        create_test_archive(True, 'path', 'to', 'some', 'nested', 'thing.jar')
        create_test_archive(False, 'path', 'to', 'some', 'nested', 'thing.txt')
        create_test_archive(True, 'another', 'nested', 'path', 'thing.tar')
        create_test_archive(True, 'another', 'nested', 'path', 'thing.zip')
        create_test_archive(True, 'another', 'nested', 'path', 'thing.tar.gz')
        create_test_archive(False, 'another', 'nested', 'path', 'thing.csv')

        analyzer = LooseArtifactAnalyzer(temp_dir)
        found_files = set()
        for f in analyzer.files_to_examine(temp_dir):
            found_files.add(f)

        assert found_files == expected_files


def test_local_lookup():
    """Test the local_lookup function correctly finds Artifacts that already exist."""
    CONTENT = 'my content'
    SHA256_SUM = '47a96905708e5470528752169f80e1d8d8b79c599ed35b0979fb9f17e9babfe6'

    checksum_node = ChecksumFactory.create(checksum=SHA256_SUM)
    artifact_node = ArtifactFactory.create(type_='rpm')
    artifact_node.checksums.connect(checksum_node)

    with tempfile.TemporaryDirectory() as temp_dir:
        jar_file = create_test_file(temp_dir, 'jar', CONTENT)
        zip_file = create_test_file(temp_dir, 'zip', 'some other content')

        analyzer = LooseArtifactAnalyzer(temp_dir)
        assert analyzer.local_lookup(jar_file) == artifact_node
        assert analyzer.local_lookup(zip_file) is None


@mock.patch('assayist.processor.loose_artifact_analyzer.LooseArtifactAnalyzer.local_lookup')
@mock.patch('assayist.processor.base.Analyzer.read_metadata_file')
def test_rpm_on_container_layer(m_read_metadata_file, m_local_lookup):
    """Test the LooseArtifactAnalyzer on an container embedding RPM content."""
    build = BuildFactory.create()
    container = ArtifactFactory.create(type_='container')
    build.artifacts.connect(container)

    m_read_metadata_file.return_value = {'id': build.id_, 'type': 'buildContainer'}
    m_local_lookup.return_value = None

    m_koji = mock.Mock()
    # Return the source artifact first, then the rpm second.
    # The bracket differences are just a matter of how the getRPM and listArchives
    # return different types of responses.
    m_koji.multiCall.side_effect = ([[[SOURCE_ARCHIVE_INFO]]], [[RPM_INFO]])

    with tempfile.TemporaryDirectory() as temp_dir:
        source_dir = os.path.join(temp_dir, 'source')
        os.makedirs(source_dir)
        layer_dir = os.path.join(
            temp_dir, 'unpacked_archives', 'container_layer', container.filename)
        test_dir = os.path.join(layer_dir, 'test_dir')
        os.makedirs(test_dir)

        source_artifact = create_test_file(source_dir, 'jar', 'asdf')
        test_file = create_test_file(test_dir, 'txt', 'dfas')
        rpm_test_file = create_test_file(test_dir, 'rpm', 'asdfasdf')

        analyzer = LooseArtifactAnalyzer(temp_dir)
        analyzer._koji_session = m_koji
        analyzer.run()

        # There's no reason to claim things in the source.
        assert os.path.exists(source_artifact) is True
        # Is not a type of file that should be found.
        assert os.path.exists(test_file) is True
        # Should have been claimed
        assert os.path.exists(rpm_test_file) is False

    assert m_read_metadata_file.call_count == 1
    assert m_koji.listArchives.call_count == 1
    assert m_koji.getRPM.call_count == 1

    container_artifact = content.Artifact.nodes.get(type_='container')  # there should be only 1
    loose_rpm_artifact = content.Artifact.nodes.get(archive_id=RPM_INFO['id'])
    source_artifact = content.Artifact.nodes.get(archive_id=SOURCE_ARCHIVE_INFO['id'])

    assert container_artifact.embedded_artifacts.is_connected(loose_rpm_artifact)
    assert container_artifact.embedded_artifacts.is_connected(source_artifact)

    # assert the build was created and connected
    build = content.Build.nodes.get(id_=str(RPM_INFO['build_id']))
    assert build.id_ == str(RPM_INFO['build_id'])
    assert build.type_ == 'build'
    assert loose_rpm_artifact.build.is_connected(build)


@mock.patch('assayist.processor.loose_artifact_analyzer.LooseArtifactAnalyzer.local_lookup')
@mock.patch('assayist.processor.base.Analyzer.read_metadata_file')
def test_archives_on_container_layer(m_read_metadata_file, m_local_lookup):
    """Test the LooseArtifactAnalyzer on a contanier embedding maven content."""
    build = BuildFactory.create()
    container = ArtifactFactory.create(type_='container')
    build.artifacts.connect(container)

    m_read_metadata_file.return_value = {'id': build.id_, 'type': 'buildContainer'}
    m_local_lookup.return_value = None

    m_koji = mock.Mock()
    # Two distinct calls. Return the source artifact first, then the embedded artifacts second.
    m_koji.multiCall.side_effect = ([[[SOURCE_ARCHIVE_INFO]]], [[[ARCHIVE_INFO1]],
                                    [[ARCHIVE_INFO2]], [[ARCHIVE_INFO3]], [[ARCHIVE_INFO4]]])

    with tempfile.TemporaryDirectory() as temp_dir:
        source_dir = os.path.join(temp_dir, 'source')
        os.makedirs(source_dir)
        layer_dir = os.path.join(
            temp_dir, 'unpacked_archives', 'container_layer', container.filename)
        test_dir = os.path.join(layer_dir, 'test_dir')
        os.makedirs(test_dir)

        source_artifact = create_test_file(source_dir, 'jar', 'some')
        test_file = create_test_file(test_dir, 'txt', 'distinct')
        jar_test_file = create_test_file(test_dir, 'jar', 'content')
        tar_test_file = create_test_file(test_dir, 'tar', 'that')
        xml_test_file = create_test_file(test_dir, 'pom.xml', 'checksums')
        pom_test_file = create_test_file(test_dir, 'pom', 'differently')

        analyzer = LooseArtifactAnalyzer(temp_dir)
        analyzer._koji_session = m_koji
        analyzer.run()

        # There's no reason to claim things in the source.
        assert os.path.exists(source_artifact) is True
        # Is not a type of file that should be found.
        assert os.path.exists(test_file) is True
        # Should have been claimed
        assert os.path.exists(jar_test_file) is False
        assert os.path.exists(tar_test_file) is False
        assert os.path.exists(xml_test_file) is False
        assert os.path.exists(pom_test_file) is False

    assert m_read_metadata_file.call_count == 1
    assert m_koji.listArchives.call_count == 5

    container_artifact = content.Artifact.nodes.get(type_='container')  # there should be only 1

    source_artifact = content.Artifact.nodes.get(archive_id=SOURCE_ARCHIVE_INFO['id'])
    assert container_artifact.embedded_artifacts.is_connected(source_artifact)

    for ARCHIVE_INFO in (ARCHIVE_INFO1, ARCHIVE_INFO2, ARCHIVE_INFO3, ARCHIVE_INFO4):
        loose_artifact = content.Artifact.nodes.get(archive_id=ARCHIVE_INFO['id'])
        assert container_artifact.embedded_artifacts.is_connected(loose_artifact)

        # assert the build was created and connected
        build = content.Build.nodes.get(id_=str(ARCHIVE_INFO['build_id']))
        assert build.id_ == str(ARCHIVE_INFO['build_id'])
        assert build.type_ == 'maven'
        assert loose_artifact.build.is_connected(build)
