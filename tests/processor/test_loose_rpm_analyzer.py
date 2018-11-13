# SPDX-License-Identifier: GPL-3.0+

import os
import tempfile

import mock

from assayist.common.models import content
from assayist.processor.loose_rpm_analyzer import LooseRpmAnalyzer
from tests.factories import BuildFactory, ArtifactFactory

RPM_INFO = {
    'arch': 'noarch',
    'build_id': 484915,
    'epoch': None,
    'id': 4177917,
    'name': 'python-django',
    'payloadhash': '217ee68c509731aef889251cae1c4b10',
    'release': '1.el7ost',
    'version': '1.8.11'
}


@mock.patch('assayist.processor.base.Analyzer.read_metadata_file')
@mock.patch('assayist.processor.loose_rpm_analyzer.LooseRpmAnalyzer._get_related_build')
def test_run_on_container_layer(m_get_build, m_read_metadata_file):
    """Test the LooseRpmAnalyzer.run() function on an unpacked container layer."""
    build = BuildFactory.create()
    container = ArtifactFactory.create(type_='container')
    build.artifacts.connect(container)

    m_read_metadata_file.return_value = {'id': 1}

    loose_rpm_build = BuildFactory.create()
    m_get_build.return_value = (loose_rpm_build, RPM_INFO)

    with tempfile.TemporaryDirectory() as temp_dir:
        layer_dir = os.path.join(
            temp_dir, 'unpacked_archives', 'container_layer', container.filename)
        test_dir = os.path.join(layer_dir, 'test_dir')
        os.makedirs(test_dir)

        test_file = os.path.join(test_dir, 'test_file.txt')
        open(test_file, 'a').close()

        rpm_test_file = os.path.join(test_dir, 'test.rpm')
        open(rpm_test_file, 'a').close()

        analyzer = LooseRpmAnalyzer(temp_dir)
        analyzer.run()

        assert os.path.exists(test_file) is True
        assert os.path.exists(rpm_test_file) is False

    assert m_read_metadata_file.call_count == 1
    assert m_get_build.call_count == 1

    container_artifact = content.Artifact.nodes.get(type_='container')  # there should be only 1
    loose_rpm_artifact = content.Artifact.nodes.get(archive_id=RPM_INFO['id'])

    assert container_artifact.embedded_artifacts.is_connected(loose_rpm_artifact)


def test_get_related_build():
    """Test the LooseRpmAnalyzer._get_related_build() function."""
    m_koji = mock.Mock()
    m_koji.getRPM.return_value = RPM_INFO

    analyzer = LooseRpmAnalyzer()
    analyzer._koji_session = m_koji

    # Create new build
    build, _ = analyzer._get_related_build('python-django-1.8.11-1.el7ost.noarch.rpm')
    assert build.id_ == str(RPM_INFO['build_id'])
    assert build.type_ == 'build'
    assert content.Build.nodes.get(id_=str(RPM_INFO['build_id']))

    # Check that no new build is created
    build, _ = analyzer._get_related_build('python-django-1.8.11-1.el7ost.noarch.rpm')
    assert len(content.Build.nodes.all()) == 1
