# SPDX-License-Identifier: GPL-3.0+

import json
import os
import pathlib
import shutil
import subprocess
import tarfile

import koji
import mock
import pytest

from assayist.processor import utils
from assayist.processor.base import Analyzer
from assayist.processor.error import (
    BuildTypeNotSupported, BuildSourceNotFound, BuildInvalidState, BuildTypeNotFound
)


def test_assert_command():
    """Test the assert_command function when the command exists."""
    with mock.patch('shutil.which', return_value=True) as mock_which:
        assert utils.assert_command('bash') is None
        mock_which.assert_called_once_with('bash')


def test_assert_command_not_found():
    """Test the assert_command function when the command doesn't exist."""
    with mock.patch('shutil.which', return_value=False) as mock_which:
        with pytest.raises(RuntimeError) as e:
            assert utils.assert_command('bash') is None
            assert str(e) == 'The command "bash" is not installed and is required'
        mock_which.assert_called_once_with('bash')


@mock.patch('assayist.processor.utils.assert_command')
@mock.patch('assayist.processor.utils.get_koji_session')
@mock.patch('assayist.processor.utils.write_file')
def test_download_build_data_full_data(m_write_file, m_get_koji_session, m_assert_command):
    """Test the download_build_data function with all available data."""
    # Setup for a 'full data' test. The actual values of most return values doesn't matter.
    PATH = '/some/path'
    BUILD_INFO = {'task_id': 2, 'id': 1, 'state': koji.BUILD_STATES['COMPLETE']}
    TASK_INFO = {'a task': 5, 'method': 'build'}
    URL = 'git+https://example.com/whatever'
    TASK_REQUEST = [URL]
    MAVEN_INFO = {'other': 'stuff'}
    RPM_INFO = [{'buildroot_id': '2'}, {'buildroot_id': '3'}]
    ARCHIVE_INFO = [{'buildroot_id': '3', 'id': '1'},
                    {'buildroot_id': '4', 'id': '2', 'btype': 'image'}]
    BUILDROOT_LISTING = [{'rpm_id': 1}, {'rpm_id': 2}]
    BUILDROOT_INFO = [[RPM_INFO[0]], [RPM_INFO[1]]]

    m_koji = mock.Mock()
    m_koji.getBuild.return_value = BUILD_INFO
    m_koji.getTaskInfo.return_value = TASK_INFO
    m_koji.getTaskRequest.return_value = TASK_REQUEST
    m_koji.getMavenBuild.return_value = MAVEN_INFO
    m_koji.listRPMs.return_value = RPM_INFO
    m_koji.listArchives.return_value = ARCHIVE_INFO
    m_koji.getBuildrootListing.return_value = BUILDROOT_LISTING
    m_koji.multiCall.return_value = BUILDROOT_INFO
    m_get_koji_session.return_value = m_koji

    utils.download_build_data(1, PATH)

    # Assert that the brew calls we expect happened.
    m_koji.getBuild.assert_called_once_with(1)
    m_koji.getTaskInfo.assert_called_once_with(2)
    m_koji.getTaskRequest.assert_called_once_with(2)
    m_koji.getMavenBuild.assert_called_once_with(1)
    # One regular and one for the image
    assert m_koji.listRPMs.call_count == 2
    m_koji.listRPMs.assert_has_calls([
        mock.call(1),
        mock.call(imageID='2'),
    ])
    m_koji.listArchives.assert_called_once_with(1)
    assert m_koji.getBuildrootListing.call_count == 3
    m_koji.getBuildrootListing.assert_has_calls([
        mock.call('2'),
        mock.call('3'),
        mock.call('4'),
    ])

    # Now assert that the data we returned was successfully written through to the files.
    # Since the second Archive is an image we expect to call listRPMs for that image
    # and write it to IMAGE_RPM_FILE.
    IMAGE_INFO = {'2': RPM_INFO}
    # The buildroot info should be repeated for each buildroot.
    ALL_BUILDROOT_INFO = {'2': RPM_INFO, '3': RPM_INFO, '4': RPM_INFO}
    # The build type was added
    BUILD_INFO['type'] = 'build'

    assert m_write_file.call_count == 7
    m_write_file.assert_has_calls([
        mock.call(TASK_INFO, PATH, Analyzer.TASK_FILE),
        mock.call(BUILD_INFO, PATH, Analyzer.BUILD_FILE),
        mock.call(MAVEN_INFO, PATH, Analyzer.MAVEN_FILE),
        mock.call(RPM_INFO, PATH, Analyzer.RPM_FILE),
        mock.call(ARCHIVE_INFO, PATH, Analyzer.ARCHIVE_FILE),
        mock.call(IMAGE_INFO, PATH, Analyzer.IMAGE_RPM_FILE),
        mock.call(ALL_BUILDROOT_INFO, PATH, Analyzer.BUILDROOT_FILE),
    ])


@mock.patch('assayist.processor.utils.assert_command')
@mock.patch('assayist.processor.utils.get_koji_session')
@mock.patch('assayist.processor.utils.write_file')
def test_download_build_data_empty_data(m_write_file, m_get_koji_session, m_assert_command):
    """Test the download_build_data function with missing data."""
    # Setup for a 'full data' test. The actual values of most return values doesn't matter.
    PATH = '/some/path'
    BUILD_INFO = {'task_id': None, 'id': 1, 'source': 'http://example.com', 'extra': {
        'container_koji_task_id': 123}, 'state': koji.BUILD_STATES['COMPLETE']}
    RPM_INFO = []
    ARCHIVE_INFO = []

    m_koji = mock.Mock()
    m_koji.getBuild.return_value = BUILD_INFO
    m_koji.getTaskInfo.return_value = None
    m_koji.getTaskRequest.return_value = None
    m_koji.getMavenBuild.return_value = None
    m_koji.listRPMs.return_value = RPM_INFO
    m_koji.listArchives.return_value = ARCHIVE_INFO
    m_koji.getBuildrootListing.return_value = None
    m_get_koji_session.return_value = m_koji

    utils.download_build_data(1, PATH)

    # Assert that the brew calls we expect happened.
    m_koji.getBuild.assert_called_once_with(1)
    assert m_koji.getTaskInfo.call_count == 0
    m_koji.getMavenBuild.assert_called_once_with(1)
    # One regular and one for the image
    m_koji.listRPMs.assert_called_once_with(1)
    m_koji.listArchives.assert_called_once_with(1)
    assert m_koji.getBuildrootListings.call_count == 0

    # Now assert that only the data we returned was successfully written through to the files.

    assert m_write_file.call_count == 1
    m_write_file.assert_has_calls([
        mock.call(BUILD_INFO, PATH, Analyzer.BUILD_FILE),
    ])


@mock.patch('assayist.processor.utils.assert_command')
@mock.patch('assayist.processor.utils.get_koji_session')
@mock.patch('assayist.processor.utils.write_file')
def test_download_build_unsupported_build_type(m_write_file, m_get_koji_session, m_assert_command):
    """Test download_build_data function for unsupported build types."""
    BUILD_INFO = {'task_id': 123, 'id': 1, 'source': 'http://some.url', 'extra': {},
                  'state': koji.BUILD_STATES['COMPLETE']}
    TASK_INFO = {'method': 'randomType'}  # I.e. value not present in Analyzer.SUPPORTED_BUILD_TYPES

    m_koji = mock.Mock()
    m_koji.getBuild.return_value = BUILD_INFO
    m_koji.getTaskInfo.return_value = TASK_INFO
    m_get_koji_session.return_value = m_koji

    with pytest.raises(BuildTypeNotSupported):
        utils.download_build_data(1, '/some/path')

    # Assert that the brew calls we expect happened.
    m_koji.getBuild.assert_called_once_with(1)
    m_koji.getTaskInfo.assert_called_once_with(123)


@mock.patch('assayist.processor.utils.assert_command')
@mock.patch('assayist.processor.utils.get_koji_session')
@mock.patch('assayist.processor.utils.write_file')
def test_download_build_unknown_type(m_write_file, m_get_koji_session, m_assert_command):
    """Test download_build_data function for build whose type cannot be determined."""
    BUILD_INFO = {'id': 1, 'source': 'http://some.url', 'extra': {},
                  'state': koji.BUILD_STATES['COMPLETE']}

    m_koji = mock.Mock()
    m_koji.getBuild.return_value = BUILD_INFO
    m_get_koji_session.return_value = m_koji

    with pytest.raises(BuildTypeNotFound):
        utils.download_build_data(1, '/some/path')

    # Assert that the brew calls we expect happened.
    m_koji.getBuild.assert_called_once_with(1)


@mock.patch('assayist.processor.utils.assert_command')
@mock.patch('assayist.processor.utils.get_koji_session')
def test_download_build_invalid_state(m_get_koji_session, m_assert_command):
    """Test download_build_data function for invalid build state."""
    BUILD_INFO = {'task_id': 123, 'id': 1, 'state': koji.BUILD_STATES['DELETED']}

    m_koji = mock.Mock()
    m_koji.getBuild.return_value = BUILD_INFO
    m_get_koji_session.return_value = m_koji

    with pytest.raises(BuildInvalidState):
        utils.download_build_data(1, '/some/path')

    # Assert that the brew calls we expect happened.
    m_koji.getBuild.assert_called_once_with(1)


@mock.patch('assayist.processor.utils.assert_command')
@mock.patch('subprocess.Popen')
def test_download_build(m_popen, m_assert_command):
    """Test the download_build function."""
    error = b''

    m_process_rpm = mock.Mock()
    output = (b'Downloading: resultsdb-2.1.0-2.el7.noarch.rpm\n'
              b'[===========================         ]  75%  64.00 KiB\r'
              b'[====================================] 100%  84.34 KiB\r\n'
              b'Downloading: resultsdb-2.1.0-2.el7.src.rpm\n'
              b'[============================        ]  80%  64.00 KiB\r'
              b'[====================================] 100%  79.61 KiB\r\n')
    m_process_rpm.communicate.return_value = (output, error)
    m_process_rpm.returncode = 0

    m_process_maven = mock.Mock()
    output = (b'Downloading: /com/eng/resultsdb-0.31.0.jar\n'
              b'[====================================] 100%  23.38 KiB\n'
              b'Downloading: /com/eng/resultsdb-doc-0.51.0.jar\n'
              b'[====================================] 100%   1.49 KiB\n')
    m_process_maven.communicate.return_value = (output, error)
    m_process_maven.returncode = 0

    m_process_image = mock.Mock()
    output = (b'No image archives available for com.some.path.resultsdb-0.31.0.jar')
    m_process_image.communicate.return_value = (output, error)
    m_process_image.returncode = 1

    process_calls = [m_process_rpm, m_process_maven, m_process_image]
    m_popen.side_effect = process_calls
    with mock.patch('os.path.isdir', return_value=True):
        rv = utils.download_build({'task_id': 2, 'id': 1}, '/some/path')

    assert rv == [
        '/some/path/resultsdb-2.1.0-2.el7.noarch.rpm',
        '/some/path/resultsdb-2.1.0-2.el7.src.rpm',
        '/some/path/com/eng/resultsdb-0.31.0.jar',
        '/some/path/com/eng/resultsdb-doc-0.51.0.jar',
    ]
    assert m_popen.call_count == 3


@pytest.mark.parametrize('url, expected_values', [
    ('git://pkgs.com/containers/rsyslog#4a4109',
     ('git://pkgs.com/containers/rsyslog', '4a4109')),
    ('git://pkgs.com/containers/rsyslog?rhel#4a4109',
     ('git://pkgs.com/containers/rsyslog', '4a4109')),
    ('git+http://pkgs.com/containers/rsyslog#4a4109',
     ('http://pkgs.com/containers/rsyslog', '4a4109')),
    ('git+https://pkgs.com/containers/rsyslog#4a4109',
     ('https://pkgs.com/containers/rsyslog', '4a4109')),
    ('git+http://code.engineering.com/gerrit/hello/world.git#rel.1.2.3',
     ('https://code.engineering.com/gerrit/hello/world.git', 'rel.1.2.3')),
    ('git+https://code.engineering.com/gerrit/hello/world.git#rel.1.2.3',
     ('https://code.engineering.com/gerrit/hello/world.git', 'rel.1.2.3')),
    ('git+ssh://user@code.engineering.com:22/hello/world.git#rel.1.2.3',
     ('https://code.engineering.com/gerrit/hello/world.git', 'rel.1.2.3')),
])
def test_parse_source_url(url, expected_values):
    """Test the parse_source_url function."""
    assert utils.parse_source_url(url) == expected_values


@mock.patch('assayist.processor.utils.assert_command')
@mock.patch('subprocess.Popen')
def test_download_source(m_popen, m_assert_command):
    """Test the download_source function."""
    build_info = {
        'id': 12345,
        'source': 'git://pkgs.com/containers/rsyslog#4a4109c3e85908b6899b1aa291570f7c7b5a0cb5',
    }

    m_process = mock.Mock()
    m_process.communicate.return_value = (b'', b'')
    m_process.returncode = 0
    m_popen.return_value = m_process

    utils.download_source(build_info, '/some/path')

    assert m_popen.call_count == 3
    assert m_process.communicate.call_count == 3

    m_popen.assert_has_calls([
        mock.call(['git', 'clone', 'git://pkgs.com/containers/rsyslog', '/some/path'],
                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE),
        mock.call().communicate(),
        mock.call(['git', 'reset', '--hard', '4a4109c3e85908b6899b1aa291570f7c7b5a0cb5'],
                  cwd='/some/path', stdout=subprocess.DEVNULL, stderr=subprocess.PIPE),
        mock.call().communicate(),
        mock.call(['rhpkg', '--user=1001', 'sources'],
                  cwd='/some/path', stdout=subprocess.DEVNULL, stderr=subprocess.PIPE),
        mock.call().communicate(),
    ])


@mock.patch('subprocess.Popen')
def test_rpm_to_cpio(m_popen):
    """Test the _rpm_to_cpio function."""
    m_process = mock.Mock()
    output = b'the cpio file'
    error = b''
    m_process.communicate.return_value = (output, error)
    m_process.returncode = 0
    m_popen.return_value = m_process
    rpm_file = '/path/to/some-rpm.rpm'
    assert utils._rpm_to_cpio(rpm_file) == output
    m_popen.assert_called_once_with(
        ['rpm2cpio', rpm_file], stderr=subprocess.PIPE, stdout=subprocess.PIPE)


@mock.patch('subprocess.Popen')
def test__unpack_cpio(m_popen):
    """Test the _unpack_cpio function."""
    m_process = mock.Mock()
    output = b''
    error = b''
    m_process.communicate.return_value = (output, error)
    m_process.returncode = 0
    m_popen.return_value = m_process
    cpio_file = b'the cpio file'
    output_dir = '/some/path'
    assert utils._unpack_cpio(cpio_file, output_dir) is None
    m_popen.assert_called_once_with(
        ['cpio', '-idmv'], cwd=output_dir, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
    m_process.communicate.assert_called_once_with(input=cpio_file)


@mock.patch('assayist.processor.utils.assert_command')
@mock.patch('assayist.processor.utils._unpack_cpio')
@mock.patch('assayist.processor.utils._rpm_to_cpio')
def test_unpack_rpm(m_rpm_to_cpio, m_unpack_cpio, m_assert_command):
    """Test the unpack_rpm function."""
    cpio = b'the cpio file'
    m_rpm_to_cpio.return_value = cpio
    rpm_file = '/path/to/some-rpm.rpm'
    output_dir = '/some/path/output/some-rpm.rpm'
    with mock.patch('os.path.isdir', return_value=False):
        utils.unpack_rpm(rpm_file, output_dir)
    m_rpm_to_cpio.assert_called_once_with(rpm_file)
    m_unpack_cpio.assert_called_once_with(cpio, output_dir)


class TestContainerUnpacking:
    """Container unpacking test with enviroment setup."""

    @staticmethod
    def _create_container_image(temp_dir):
        """Create a minimal container image TAR file that contains all the expected contents.

        docker-image:sha123
        ├── 012cd57ae
        │   ├── json
        │   ├── layer.tar
        │   │   ├── a  (contains string "012cd57ae")
        │   │   ├── b  (contains string "012cd57ae")
        │   │   └── c  (contains string "012cd57ae")
        │   └── VERSION
        ├── 09085539f
        │   ├── json
        │   ├── layer.tar
        │   │   ├── a  (contains string "09085539f")
        │   │   ├── b  (contains string "09085539f")
        │   │   └── c  (contains string "09085539f")
        │   └── VERSION
        ├── f773f81ef
        │   ├── json
        │   ├── layer.tar
        │   │   ├── a  (contains string "f773f81ef")
        │   │   ├── b  (contains string "f773f81ef")
        │   │   └── c  (contains string "f773f81ef")
        │   └── VERSION
        └── manifest.json

        :param temp_dir: temporary directory in which we create the container image
        """
        layers = ['012cd57ae', 'f773f81ef', '09085539f']
        fake_manifest = json.dumps([{
            'Config': 'a1cea2fe.json',
            'RepoTags': ['some-tag'],
            'Layers': [layer + '/layer.tar' for layer in layers],
        }])

        image_path = pathlib.Path(temp_dir.join('container_image'))

        for layer in layers:
            path = image_path / layer
            path.mkdir(parents=True)

            for file_ in ('VERSION', 'json'):
                with open(path / file_, 'w') as f:
                    f.write('test')

            layer_path = path / 'layer'
            layer_path.mkdir()
            for file_ in 'a b c'.split():
                with open(layer_path / file_, 'w') as f:
                    f.write(layer)

            with tarfile.open(path / 'layer.tar', mode='w') as archive:
                archive.add(layer_path, arcname='')

            shutil.rmtree(layer_path)

        with open(image_path / 'manifest.json', 'w') as f:
            f.write(fake_manifest)

        with tarfile.open(temp_dir.join('docker-image:sha123.tar.gz'), mode='w:gz') as archive:
            archive.add(image_path, recursive=True, arcname='')

        shutil.rmtree(image_path)

    @pytest.fixture()
    def temp_container_dir(self, tmpdir_factory):
        """Create a temporary directory with a fake container image for testing.

        :param tmpdir_factory: pytest fixture that sets up a temporary directory
        :return: temporary directory that is used for tests
        """
        temp_dir = tmpdir_factory.mktemp("data")

        self._create_container_image(temp_dir)
        pathlib.Path(temp_dir / 'output').mkdir()

        return temp_dir

    def test_file(self, temp_container_dir):
        """Test the unpack_container_image function."""
        utils.unpack_container_image(temp_container_dir.join('docker-image:sha123.tar.gz'),
                                     temp_container_dir.join('output'))

        assert set(os.listdir(temp_container_dir)) == {'output', 'docker-image:sha123.tar.gz'}
        assert set(os.listdir(temp_container_dir.join('output'))) == {'a', 'b', 'c'}
        with open(temp_container_dir.join('output').join('a')) as f:
            assert f.read() == '09085539f'


def _mocked_iszipfile(filename):
    return '.jar' in filename


def _mocked_istarfile(filename):
    return '.tar' in filename


@mock.patch('os.makedirs')
@mock.patch('assayist.processor.utils.unpack_rpm')
@mock.patch('assayist.processor.utils.unpack_container_image')
@mock.patch('assayist.processor.utils.unpack_zip')
@mock.patch('assayist.processor.utils.unpack_tar')
@mock.patch('tarfile.is_tarfile', new=_mocked_istarfile)
@mock.patch('zipfile.is_zipfile', new=_mocked_iszipfile)
def test_unpack_artifacts(m_unpack_tar, m_unpack_zip, m_unpack_container_image,
                          m_unpack_rpm, m_makedirs):
    """Test the unpack_artifacts."""
    artifacts = ['/path/to/some-rpm.rpm', '/path/to/some-rpm.src.rpm',
                 'path/to/some-jar.jar',
                 'path/to/docker-image:123.tar.gz',
                 'path/to/some-tar-file.tar']
    output_dir = '/path/to/output'

    with mock.patch('os.path.isdir', return_value=True):
        with mock.patch('os.path.isfile', return_value=True):
            utils.unpack_artifacts(artifacts, output_dir)

    rpm_dirs = [f'{output_dir}/rpm/some-rpm.rpm', f'{output_dir}/rpm/some-rpm.src.rpm']
    container_dir = f'{output_dir}/container_layer/docker-image:123.tar.gz'
    non_rpm_dirs = [f'{output_dir}/non-rpm/some-jar.jar', f'{output_dir}/non-rpm/some-tar-file.tar']

    m_unpack_rpm.assert_has_calls([
        mock.call(artifacts[0], rpm_dirs[0]),
        mock.call(artifacts[1], rpm_dirs[1]),
    ])
    m_unpack_zip.assert_called_once_with(artifacts[2], non_rpm_dirs[0])
    m_unpack_container_image.assert_called_once_with(artifacts[3], container_dir)
    m_unpack_tar.assert_called_once_with(artifacts[4], non_rpm_dirs[1])

    m_makedirs.assert_has_calls(
        [mock.call(rpm_dirs[0]), mock.call(rpm_dirs[1]), mock.call(non_rpm_dirs[0]),
         mock.call(container_dir), mock.call(non_rpm_dirs[1])]
    )


@pytest.mark.parametrize('build_info,task_request,expected', [
    (
        {'id': 1, 'source': 'git://domain.local/rpms/pkg', 'task_id': 123},
        [],
        'git://domain.local/rpms/pkg'
    ),
    (
        {'id': 1, 'source': None, 'task_id': 123},
        ['red', 'git://domain.local/rpms/pkg', 'sox'],
        'git://domain.local/rpms/pkg'
    ),
    (
        {'id': 1, 'source': None, 'task_id': 123},
        ['red', {'ksurl': 'git://domain.local/rpms/pkg', 'red': 'sox'}, 'green'],
        'git://domain.local/rpms/pkg'
    ),
])
@mock.patch('assayist.processor.utils.get_koji_session')
def test_get_source_of_build(mock_session, build_info, task_request, expected):
    """Test that get_source_of_build can find the source of build using heuristics."""
    mock_session.return_value.getTaskRequest.return_value = task_request
    assert utils.get_source_of_build(build_info) == expected


@pytest.mark.parametrize('build_info,task_request', [
    ({'id': 1}, []),  # No build source, no task ID
    ({'id': 1, 'task_id': 123}, None),  # No build source, empty task request
    ({'id': 1, 'task_id': 123}, {}),  # No build source, unexpected return value (should be list)
    ({'id': 1, 'task_id': 123}, {'hello': 'world'}),  # No build source, source not found in dict
])
@mock.patch('assayist.processor.utils.get_koji_session')
def test_get_source_of_build_missing_source(mock_session, build_info, task_request):
    """Test that get_source_of_build can find the source of build using heuristics."""
    mock_session.return_value.getTaskRequest.return_value = task_request

    with pytest.raises(BuildSourceNotFound):
        utils.get_source_of_build(build_info)


@pytest.mark.parametrize('build_info,task_info,expected', [
    ({'extra': None}, {'method': 'build'}, 'build'),
    ({'extra': None}, {}, None),
    ({'extra': {}}, {}, None),
    ({'extra': {'typeinfo': {}}}, {}, None),
    ({'extra': {'typeinfo': {'module': {'x': 1}}}}, {}, 'module'),
    ({'extra': {'something': []}}, {}, None),
    ({'extra': {'container_koji_task_id': 12345}}, {}, 'buildContainer'),
    ({'extra': {'maven': {'version': 1}}}, {}, 'maven'),
])
def test_get_build_type(build_info, task_info, expected):
    """Test the heuristics of determining the build type in get_build_type()."""
    assert utils.get_build_type(build_info, task_info) == expected
