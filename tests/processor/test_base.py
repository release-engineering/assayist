# SPDX-License-Identifier: GPL-3.0+

import tempfile
import os

import pytest

from assayist.processor.base import Analyzer as BaseAnalyzer
from assayist.common.models.source import Component


class DummyAnalyzer(BaseAnalyzer):
    """A dummy analyzer to test non-static methods."""

    def run(self):
        """Do nothing."""
        return


def test_claim_container_file():
    """Test that the claim_container_file method does nothing on a directory and deletes a file."""
    container_file_name = 'docker-image-123456'
    with tempfile.TemporaryDirectory() as temp_dir:
        layer_dir = os.path.join(
            temp_dir, 'unpacked_archives', 'container_layer', container_file_name)
        test_dir = os.path.join(layer_dir, 'test_dir')
        os.makedirs(test_dir)
        test_file = os.path.join(test_dir, 'test_file.txt')
        with open(test_file, 'w+') as f:
            f.write('something')

        analyzer = DummyAnalyzer(temp_dir)
        archive = {'filename': container_file_name}
        analyzer.claim_container_file(archive, '/test_dir')
        assert os.path.exists(test_dir) is True
        analyzer.claim_container_file(archive, '/test_dir/test_file.txt')
        assert os.path.exists(test_dir) is True
        assert os.path.exists(test_file) is False


def test_claim_container_file_through_symlink():
    """Test that the claim_container_file method follows a symlink properly."""
    container_file_name = 'docker-image-123456'
    with tempfile.TemporaryDirectory() as temp_dir:
        layer_dir = os.path.join(
            temp_dir, 'unpacked_archives', 'container_layer', container_file_name)
        test_dir = os.path.join(layer_dir, 'test_dir')
        os.makedirs(test_dir)
        test_file = os.path.join(test_dir, 'test_file.txt')
        with open(test_file, 'w+') as f:
            f.write('something')
        test_symlink = os.path.join(layer_dir, 'test_symlink')
        os.symlink('/test_dir', test_symlink)

        analyzer = DummyAnalyzer(temp_dir)
        archive = {'filename': container_file_name}
        analyzer.claim_container_file(archive, '/test_symlink/test_file.txt')
        assert os.path.exists(test_dir) is True
        assert os.path.exists(test_file) is False


def test_claim_container_file_through_multiple_symlink():
    """Test that the claim_container_file method follows multiple symlinks properly."""
    container_file_name = 'docker-image-123456'
    with tempfile.TemporaryDirectory() as temp_dir:
        layer_dir = os.path.join(
            temp_dir, 'unpacked_archives', 'container_layer', container_file_name)
        test_dir = os.path.join(layer_dir, 'test_dir')
        test_subdir = os.path.join(test_dir, 'test_subdir')
        os.makedirs(test_subdir)
        test_file = os.path.join(test_subdir, 'test_file.txt')
        with open(test_file, 'w+') as f:
            f.write('something')
        test_symlink = os.path.join(layer_dir, 'test_symlink')
        os.symlink('/test_dir', test_symlink)
        test_symlink2 = os.path.join(test_dir, 'test_symlink2')
        os.symlink('/test_dir/test_subdir', test_symlink2)

        analyzer = DummyAnalyzer(temp_dir)
        archive = {'filename': container_file_name}
        analyzer.claim_container_file(archive, '/test_symlink/test_symlink2/test_file.txt')
        assert os.path.exists(test_subdir) is True
        assert os.path.exists(test_file) is False


def test_component_invalid_get_or_create():
    """Ensure that the Component get_or_create method is not avialable."""
    with pytest.raises(RuntimeError):
        Component.get_or_create({
            'canonical_namespace': 'a',
            'canonical_name': 'kernel',
            'canonical_type': 'rpm'})


def test_component_invalid_create_or_update():
    """Ensure that the Component create_or_update method is not avialable."""
    with pytest.raises(RuntimeError):
        Component.create_or_update({
            'canonical_namespace': 'a',
            'canonical_name': 'kernel',
            'canonical_type': 'rpm'})


def test_component_get_or_create_singleton():
    """Ensure that the Component.get_or_create_singleton method works correctly."""
    c1 = Component.get_or_create_singleton('', 'requests', 'rpm')
    assert c1.id  # Is saved.
    assert c1.canonical_namespace == ''
    assert c1.canonical_name == 'requests'
    assert c1.canonical_type == 'rpm'

    c1.alternative_names = ['python2-requests', 'python2-requests']
    c1.save()

    # Same name as before
    c2 = Component.get_or_create_singleton('', 'requests', 'rpm')
    assert c1 == c2

    # Different name, but in the alternatives list
    c3 = Component.get_or_create_singleton('', 'python2-requests', 'rpm')
    assert c1 == c3


def create_test_file(test_dir, extension, content):
    """Touch files in the test directory."""
    x = os.path.join(test_dir, 'test_file.' + extension)
    with open(x, 'a') as f:
        f.write(content)
    return x


def test_walk():
    """Test the walk method correctly discoveres all files it's supposed to."""
    expected_files = set()
    expected_list = []
    with tempfile.TemporaryDirectory() as temp_dir:
        def create_test_archive(expected, *args):
            global num_expected
            new_dir = os.path.join(temp_dir, *args[:-1])
            try:
                os.makedirs(new_dir)
            except FileExistsError:
                pass
            f = create_test_file(new_dir, args[-1], 'content')
            if expected:
                expected_files.add(f)
                expected_list.append(f)

        extensions = ['.rpm', '.jar', '.tar', '.zip', '.tar.gz', '.kar']
        create_test_archive(True, 'path', 'to', 'some', 'nested', 'thing.rpm')
        create_test_archive(True, 'path', 'to', 'some', 'nested', 'thing.jar')
        create_test_archive(False, 'path', 'to', 'some', 'nested', 'thing.txt')
        create_test_archive(True, 'another', 'nested', 'path', 'thing.tar')
        create_test_archive(True, 'another', 'nested', 'path', 'thing.zip')
        create_test_archive(True, 'another', 'nested', 'path', 'thing.tar.gz')
        create_test_archive(False, 'another', 'nested', 'path', 'thing.csv')
        # Directory that has an "extension" should not be found, but files in it should be.
        create_test_archive(True, 'path', 'with', 'weird', 'dirname.jar', 'thing.kar')
        # Note that the next two symlinks intentionally create a loop.
        os.symlink(os.path.join(temp_dir, 'another', 'nested'),
                   os.path.join(temp_dir, 'path', 'to', 'dir'),
                   target_is_directory=True)
        os.symlink(os.path.join(temp_dir, 'path', 'to'),
                   os.path.join(temp_dir, 'another', 'nested', 'dir'),
                   target_is_directory=True)
        os.symlink(os.path.join(temp_dir, 'another', 'nested', 'path', 'thing.tar'),
                   os.path.join(temp_dir, 'path', 'to', 'file'))

        found_files = set()
        found_list = []
        analyzer = DummyAnalyzer(temp_dir)
        for f in analyzer.walk(temp_dir, extensions=extensions):
            found_files.add(f)
            found_list.append(f)

        assert found_files == expected_files
        assert len(found_list) == len(expected_list)
