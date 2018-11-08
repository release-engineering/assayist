# SPDX-License-Identifier: GPL-3.0+

import os
import tempfile

import mock

from assayist.common.models import content
from assayist.processor.post_analyzer import PostAnalyzer
from tests.factories import ArtifactFactory


@mock.patch('assayist.processor.base.Analyzer.read_metadata_file')
@mock.patch('assayist.processor.post_analyzer.PostAnalyzer.sha256_checksum')
def test_run_one_unknown_file(m_sha256_checksum, m_read_metadata_file):
    """Test the PostAnalyzer.run() function."""
    container = ArtifactFactory.create(type_='container')
    m_read_metadata_file.return_value = {
        'id': 1234,
        'extra': {'container_koji_task_id': 123456, 'image': {}},
    }
    m_sha256_checksum.return_value = 'cafebabe'

    with tempfile.TemporaryDirectory() as temp_dir:
        layer_dir = os.path.join(
            temp_dir, 'unpacked_archives', 'container_layer', container.filename)
        test_dir = os.path.join(layer_dir, 'test_dir')
        os.makedirs(test_dir)

        test_file = os.path.join(test_dir, 'test_file.txt')
        open(test_file, 'a').close()

        analyzer = PostAnalyzer(temp_dir)
        analyzer.run()

    assert m_read_metadata_file.call_count == 1
    assert m_sha256_checksum.call_count == 1

    assert len(content.UnknownFile.nodes.all()) == 1

    unknown_file = content.UnknownFile.nodes.first()
    assert unknown_file.checksum == 'cafebabe'
    assert unknown_file.filename == 'test_file.txt'
    assert unknown_file.path == '/test_dir'
