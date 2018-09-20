# SPDX-License-Identifier: GPL-3.0+

import subprocess

import mock
import pytest

from assayist.processor import utils


def test_assert_command():
    """Test the _assert_command function when the command exists."""
    with mock.patch('shutil.which', return_value=True) as mock_which:
        assert utils._assert_command('bash') is None
        mock_which.assert_called_once_with('bash')


def test_assert_command_not_found():
    """Test the _assert_command function when the command doesn't exist."""
    with mock.patch('shutil.which', return_value=False) as mock_which:
        with pytest.raises(RuntimeError) as e:
            assert utils._assert_command('bash') is None
            assert str(e) == 'The command "bash" is not installed and is required'
        mock_which.assert_called_once_with('bash')


@mock.patch('assayist.processor.utils._assert_command')
@mock.patch('assayist.processor.utils.get_koji_session')
@mock.patch('subprocess.Popen')
def test_download_build(m_popen, m_get_koji_session, m_assert_command):
    """Test the download_build function."""
    m_koji_session = mock.Mock()
    m_koji_session.getBuild.return_value = {
        'id': 12345,
        'task_id': 23456
    }
    m_koji_session.getTaskInfo.return_value = {'method': 'build'}
    m_get_koji_session.return_value = m_koji_session
    m_process = mock.Mock()
    output = (b'Downloading: resultsdb-2.1.0-2.el7.noarch.rpm\n'
              b'[===========================         ]  75%  64.00 KiB\r'
              b'[====================================] 100%  84.34 KiB\r\n'
              b'Downloading: resultsdb-2.1.0-2.el7.src.rpm\n'
              b'[============================        ]  80%  64.00 KiB\r'
              b'[====================================] 100%  79.61 KiB\r\n')
    error = b''
    m_process.communicate.return_value = (output, error)
    m_process.returncode = 0
    m_popen.return_value = m_process
    with mock.patch('os.path.isdir', return_value=True):
        rv = utils.download_build(12345, '/some/path')
    assert rv == [
        '/some/path/resultsdb-2.1.0-2.el7.noarch.rpm',
        '/some/path/resultsdb-2.1.0-2.el7.src.rpm'
    ]
    m_koji_session.getBuild.assert_called_once_with(12345)
    m_koji_session.getTaskInfo.assert_called_once_with(23456)


@pytest.mark.parametrize('method_type,expected', [
    ('build', ['koji', '--profile', 'brew', 'download-build', '12345']),
    ('maven', ['koji', '--profile', 'brew', 'download-build', '12345', '--type', 'maven'])
])
@mock.patch('assayist.processor.utils._assert_command')
@mock.patch('assayist.processor.utils.get_koji_session')
@mock.patch('subprocess.Popen')
def test_download_build_args(m_popen, m_get_koji_session, m_assert_command, method_type, expected):
    """Test the "koji download-build" arguments generated in the download_build function."""
    m_koji_session = mock.Mock()
    m_koji_session.getBuild.return_value = {
        'id': 12345,
        'task_id': 23456
    }
    m_koji_session.getTaskInfo.return_value = {
        'method': method_type
    }
    m_get_koji_session.return_value = m_koji_session
    m_process = mock.Mock()
    # The output isn't tested here since it's tested in test_download_build
    m_process.communicate.return_value = (b'', b'')
    m_process.returncode = 0
    m_popen.return_value = m_process
    with mock.patch('os.path.isdir', return_value=True):
        utils.download_build(12345, '/some/path')
    m_popen.assert_called_once_with(expected, cwd='/some/path', stdout=subprocess.PIPE)


@mock.patch('assayist.processor.utils._assert_command')
@mock.patch('assayist.processor.utils.get_koji_session')
@mock.patch('subprocess.Popen')
def test_download_build_args_container(m_popen, m_get_koji_session, m_assert_command):
    """Test the "koji download-build" arguments for a container."""
    m_koji_session = mock.Mock()
    m_koji_session.getBuild.return_value = {
        'id': 12345,
        'task_id': None,
        'extra': {'container_koji_task_id': 23456}
    }
    m_get_koji_session.return_value = m_koji_session
    m_process = mock.Mock()
    # The output isn't tested here since it's tested in test_download_build
    m_process.communicate.return_value = (b'', b'')
    m_process.returncode = 0
    m_popen.return_value = m_process
    with mock.patch('os.path.isdir', return_value=True):
        utils.download_build(12345, '/some/path')
    expected = ['koji', '--profile', 'brew', 'download-build', '12345', '--type', 'image']
    m_popen.assert_called_once_with(expected, cwd='/some/path', stdout=subprocess.PIPE)


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


@mock.patch('assayist.processor.utils._assert_command')
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


@mock.patch('os.mkdir')
@mock.patch('assayist.processor.utils.unpack_rpm')
def test_unpack_artifacts(m_unpack_rpm, m_mkdir):
    """Test the unpack_artifacts."""
    artifacts = ['/path/to/some-rpm.rpm', '/path/to/some-rpm.src.rpm']
    output_dir = '/path/to/output'
    with mock.patch('os.path.isdir', side_effect=[True, False, False]):
        with mock.patch('os.path.isfile', return_value=True):
            utils.unpack_artifacts(artifacts, output_dir)
    rpm_dirs = [f'{output_dir}/some-rpm.rpm', f'{output_dir}/some-rpm.src.rpm']
    m_unpack_rpm.assert_has_calls([
        mock.call(artifacts[0], rpm_dirs[0]),
        mock.call(artifacts[1], rpm_dirs[1])])
    assert m_unpack_rpm.call_count == 2
    m_mkdir.assert_has_calls([mock.call(rpm_dirs[0]), mock.call(rpm_dirs[1])])
