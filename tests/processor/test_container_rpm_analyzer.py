# SPDX-License-Identifier: GPL-3.0+

import mock

from assayist.processor.container_rpm_analyzer import ContainerRPMAnalyzer
from assayist.common.models import content


def test_get_rpms_diff():
    """Test that the _get_rpms_diff method returns the correct output."""
    mock_session = mock.Mock()
    mock_session.listRPMs.side_effect = [
        [{'id': 123}, {'id': 124}],
        [{'id': 123}, {'id': 124}, {'id': 125}, {'id': 126}],
    ]
    expected = [{'id': 125}, {'id': 126}]
    analyzer = ContainerRPMAnalyzer()
    analyzer._koji_session = mock_session
    assert analyzer._get_rpms_diff(1, 2) == expected


@mock.patch('assayist.processor.container_rpm_analyzer.Analyzer.claim_container_file')
def test_process_embedded_rpms(mock_claim_cf):
    """Test that the _process_embedded_rpms method creates the correct entries in Neo4j."""
    mock_session = mock.Mock()
    mock_session.multiCall.return_value = [
        [[{'name': '/etc/app/app.conf'}, {'name': '/usr/bin/app'}]],
        [[{'name': '/etc/app2/app.conf'}, {'name': '/usr/bin/app2'}]],
    ]
    archive = {'id': 1234, 'btype': 'container', 'extra': {'image': {'arch': 'x86_64'}}}
    rpms = [
        {
            'id': 34,
            'name': 'app',
            'version': '1.2.3',
            'release': 1,
            'arch': 'x86_64',
            'payloadhash': '123456789abcdef',
            'build_id': 2,
        },
        {
            'id': 35,
            'name': 'app2',
            'version': '2.3.4',
            'release': 1,
            'arch': 'x86_64',
            'payloadhash': '3456789abcdef12',
            'build_id': 3,
        }
    ]

    analyzer = ContainerRPMAnalyzer()
    analyzer._koji_session = mock_session
    analyzer._process_embedded_rpms(archive, rpms)

    container = content.Artifact.nodes.get_or_none(archive_id=1234, type_='container')
    assert container is not None
    # Make sure the two RPMs that were passed in are embedded in the container
    assert len(container.embedded_artifacts) == 2
    embedded_artifact, embedded_artifact2 = container.embedded_artifacts.all()
    assert embedded_artifact.archive_id == '35'
    assert embedded_artifact.architecture == 'x86_64'
    assert embedded_artifact.filename == 'app2-2.3.4-1.x86_64.rpm'
    assert embedded_artifact.type_ == 'rpm'
    assert embedded_artifact.checksums[0].checksum == '3456789abcdef12'
    assert embedded_artifact2.archive_id == '34'
    assert embedded_artifact2.architecture == 'x86_64'
    assert embedded_artifact2.filename == 'app-1.2.3-1.x86_64.rpm'
    assert embedded_artifact2.type_ == 'rpm'
    assert embedded_artifact2.checksums[0].checksum == '123456789abcdef'
    # Make sure claim_container_file was called once for each RPM file
    assert mock_claim_cf.call_count == 4


@mock.patch('assayist.processor.base.Analyzer.read_metadata_file')
@mock.patch('assayist.processor.container_rpm_analyzer.ContainerRPMAnalyzer._get_rpms_diff')
@mock.patch('assayist.processor.container_rpm_analyzer.ContainerRPMAnalyzer._process_embedded_rpms')
def test_run(mock_p_e_rpms, mock_get_diff, mock_read_md_file):
    """Test the core logic in the run method when the image isn't a base image."""
    mock_session = mock.Mock()
    mock_session.listArchives.return_value = [
        {
            'id': 3,
            'extra': {'image': {'arch': 'x86_64'}},
            'filename': 'docker-image-sha256-523456789abcde4',
            'btype': 'image',
        },
        {
            'id': 4,
            'extra': {'image': {'arch': 's390x'}},
            'filename': 'docker-image-sha256-63456789abcdef2',
            'btype': 'image',
        }
    ]

    mock_read_md_file.side_effect = [
        {
            'id': 1234,
            'extra': {'container_koji_task_id': 123456, 'image': {'parent_build_id': 22}}
        },
        [
            {
                'id': 1,
                'extra': {'image': {'arch': 'x86_64'}},
                'filename': 'docker-image-sha256-123456789abcdef',
                'btype': 'image',
            },
            {
                'id': 2,
                'extra': {'image': {'arch': 's390x'}},
                'filename': 'docker-image-sha256-33456789abcdef2',
                'btype': 'image',
            }
        ]
    ]

    analyzer = ContainerRPMAnalyzer()
    analyzer._koji_session = mock_session
    analyzer.run()
    # Make sure read_metadata_file was called twice, once for the build info and the other for the
    # archives
    assert mock_read_md_file.call_count == 2
    # Make sure _process_embedded_rpms and _get_rpms_diff were called twice, once for each arch
    assert mock_p_e_rpms.call_count == 2
    assert mock_get_diff.call_count == 2
    # Make sure listArchives was called once for the parent
    mock_session.listArchives.assert_called_once()


@mock.patch('assayist.processor.base.Analyzer.read_metadata_file')
@mock.patch('assayist.processor.container_rpm_analyzer.ContainerRPMAnalyzer._get_rpms_diff')
@mock.patch('assayist.processor.container_rpm_analyzer.ContainerRPMAnalyzer._process_embedded_rpms')
def test_run_parent_image(mock_p_e_rpms, mock_get_diff, mock_read_md_file):
    """Test the core logic in the run method when the image is a base image (no parent)."""
    mock_session = mock.Mock()
    mock_read_md_file.side_effect = [
        {
            'id': 1234,
            'extra': {'container_koji_task_id': 123456, 'image': {}}
        },
        [
            {
                'id': 3,
                'extra': {'image': {'arch': 'x86_64'}},
                'filename': 'docker-image-sha256-523456789abcde4',
                'btype': 'image',
            },
            {
                'id': 4,
                'extra': {'image': {'arch': 's390x'}},
                'filename': 'docker-image-sha256-63456789abcdef2',
                'btype': 'image',
            }
        ],
        {
            3: [{'id': 111, 'name': 'kernel'}],
            4: [{'id': 222, 'name': 'kernel'}],
        },
    ]

    analyzer = ContainerRPMAnalyzer()
    analyzer._koji_session = mock_session
    analyzer.run()
    # Make sure read_metadata_file was called three times, once for the build info, once for the
    # archives, and once for the image rpms.
    assert mock_read_md_file.call_count == 3
    # Make sure _process_embedded_rpms was called twice, once for each arch
    assert mock_p_e_rpms.call_count == 2
    # Make sure listArchives was not called since that information is cached for the current layer
    mock_session.listArchives.assert_not_called()
    # Make sure _get_rpms_diff was not called since that only gets called when the image has a
    # parent
    mock_get_diff.assert_not_called()
