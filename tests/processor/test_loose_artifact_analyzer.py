# SPDX-License-Identifier: GPL-3.0+

import os
import tempfile

import mock

from assayist.common.models import content
from assayist.processor.loose_artifact_analyzer import LooseArtifactAnalyzer
from tests.factories import BuildFactory, ArtifactFactory

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

ARCHIVE_INFO = {
    'build_id': 390982,
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
    'id': 778934,
    'size': 3320
}


def test_batches():
    """Test that the batching function works properly."""
    analyzer = LooseArtifactAnalyzer()
    analyzer.KOJI_BATCH_SIZE = 2
    it = set([1, 2, 3, 4, 5])
    ret = analyzer.batches(it)
    assert len(ret) == 3
    it2 = set()
    for x, y in ret:
        it2.add(x)
        if y:
            it2.add(y)

    assert it == it2


@mock.patch('assayist.processor.base.Analyzer.read_metadata_file')
def test_rpm_on_container_layer(m_read_metadata_file):
    """Test the LooseArtifactAnalyzer on an container embedding RPM content."""
    build = BuildFactory.create()
    container = ArtifactFactory.create(type_='container')
    build.artifacts.connect(container)

    m_read_metadata_file.return_value = {'id': 1, 'type': 'buildContainer'}

    m_koji = mock.Mock()
    m_koji.multiCall.return_value = [[RPM_INFO]]

    with tempfile.TemporaryDirectory() as temp_dir:
        layer_dir = os.path.join(
            temp_dir, 'unpacked_archives', 'container_layer', container.filename)
        test_dir = os.path.join(layer_dir, 'test_dir')
        os.makedirs(test_dir)

        test_file = os.path.join(test_dir, 'test_file.txt')
        open(test_file, 'a').close()

        rpm_test_file = os.path.join(test_dir, 'test.rpm')
        open(rpm_test_file, 'a').close()

        analyzer = LooseArtifactAnalyzer(temp_dir)
        analyzer._koji_session = m_koji
        analyzer.run()

        assert os.path.exists(test_file) is True
        assert os.path.exists(rpm_test_file) is False

    assert m_read_metadata_file.call_count == 1
    assert m_koji.getRPM.call_count == 1

    container_artifact = content.Artifact.nodes.get(type_='container')  # there should be only 1
    loose_rpm_artifact = content.Artifact.nodes.get(archive_id=RPM_INFO['id'])

    assert container_artifact.embedded_artifacts.is_connected(loose_rpm_artifact)

    # assert the build was created and connected
    build = content.Build.nodes.get(id_=str(RPM_INFO['build_id']))
    assert build.id_ == str(RPM_INFO['build_id'])
    assert build.type_ == 'build'
    assert loose_rpm_artifact.build.is_connected(build)


@mock.patch('assayist.processor.base.Analyzer.read_metadata_file')
def test_archives_on_container_layer(m_read_metadata_file):
    """Test the LooseArtifactAnalyzer on a contanier embedding maven content."""
    build = BuildFactory.create()
    container = ArtifactFactory.create(type_='container')
    build.artifacts.connect(container)

    m_read_metadata_file.return_value = {'id': 1, 'type': 'buildContainer'}

    m_koji = mock.Mock()
    m_koji.multiCall.return_value = [[[ARCHIVE_INFO]]]

    with tempfile.TemporaryDirectory() as temp_dir:
        layer_dir = os.path.join(
            temp_dir, 'unpacked_archives', 'container_layer', container.filename)
        test_dir = os.path.join(layer_dir, 'test_dir')
        os.makedirs(test_dir)

        def create_test_file(extension):
            x = os.path.join(test_dir, 'test_file.' + extension)
            open(x, 'a').close()
            return x

        test_file = create_test_file('txt')
        jar_test_file = create_test_file('jar')
        tar_test_file = create_test_file('tar')
        xml_test_file = create_test_file('pom.xml')
        pom_test_file = create_test_file('pom')

        analyzer = LooseArtifactAnalyzer(temp_dir)
        analyzer._koji_session = m_koji
        analyzer.run()

        assert os.path.exists(test_file) is True
        assert os.path.exists(jar_test_file) is False
        assert os.path.exists(tar_test_file) is False
        assert os.path.exists(xml_test_file) is False
        assert os.path.exists(pom_test_file) is False

    assert m_read_metadata_file.call_count == 1
    assert m_koji.listArchives.call_count == 4

    container_artifact = content.Artifact.nodes.get(type_='container')  # there should be only 1
    # We connected four "files" but since the mock method returned the same archive_info for
    # each it's okay that there's only one result here.
    loose_artifact = content.Artifact.nodes.get(archive_id=ARCHIVE_INFO['id'])
    assert container_artifact.embedded_artifacts.is_connected(loose_artifact)

    # assert the build was created and connected
    build = content.Build.nodes.get(id_=str(ARCHIVE_INFO['build_id']))
    assert build.id_ == str(ARCHIVE_INFO['build_id'])
    assert build.type_ == 'maven'
    assert loose_artifact.build.is_connected(build)
