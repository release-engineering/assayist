# SPDX-License-Identifier: GPL-3.0+

import json
import os
import pathlib
import shutil
import subprocess
import tarfile

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
    }

    m_get_koji_session.return_value = m_koji_session
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
        rv, _ = utils.download_build(12345, '/some/path')

    assert rv == [
        '/some/path/resultsdb-2.1.0-2.el7.noarch.rpm',
        '/some/path/resultsdb-2.1.0-2.el7.src.rpm',
        '/some/path/com/eng/resultsdb-0.31.0.jar',
        '/some/path/com/eng/resultsdb-doc-0.51.0.jar',
    ]
    assert m_popen.call_count == 3
    m_koji_session.getBuild.assert_called_once_with(12345)


@mock.patch('assayist.processor.utils._assert_command')
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

    assert m_popen.call_count == 2
    assert m_process.communicate.call_count == 2

    m_popen.assert_has_calls([
        mock.call(['git', 'clone', 'git://pkgs.com/containers/rsyslog'], cwd='/some/path',
                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE),
        mock.call().communicate(),
        mock.call(['git', 'reset', '--hard', '4a4109c3e85908b6899b1aa291570f7c7b5a0cb5'],
                  cwd='/some/path/rsyslog', stdout=subprocess.DEVNULL, stderr=subprocess.PIPE),
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
