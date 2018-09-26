# SPDX-License-Identifier: GPL-3.0+

import mock
import pytest

from assayist.processor import base, main_analyzer
from assayist.common.models.source import Component, SourceLocation
from assayist.common.models.content import Artifact, Build

#RPM INFO BLOBS
VIM_1_2_3 = {'buildroot_id': '1',
             'id': '1',
             'name': 'vim',
             'epoch': '1',
             'version': '2',
             'release': '3.el7',
             'arch': 'x86_64',
             'payloadhash': '1234567890'}

VIM_2_3 = {'buildroot_id': '1',
           'id': '2',
           'name': 'vim',
           'epoch': None,
           'version': '2',
           'release': '3.el7',
           'arch': 'x86_64',
           'payloadhash': '1234567890'}

SSH_9_8_7 = {'buildroot_id': '2',
             'id': '3',
             'name': 'ssh',
             'epoch': '9',
             'version': '8',
             'release': '7.el7',
             'arch': 'x86_64',
             'payloadhash': '0987654321'}

NETWORKMANAGER_5_6_7_X86 = {'id': '4',
                            'name': 'NetworkManager',
                            'epoch': '5',
                            'version': '6',
                            'release': '7.el7',
                            'arch': 'x86_64',
                            'payloadhash': '1234567890'}

NETWORKMANAGER_5_6_7_PPC = {'id': '5',
                            'name': 'NetworkManager',
                            'epoch': '5',
                            'version': '6',
                            'release': '7.el7',
                            'arch': 'ppc64le',
                            'payloadhash': '1234567890'}

GCC_2_3_4 = {'id': '6',
             'name': 'gcc',
             'epoch': '2',
             'version': '3',
             'release': '4.el7',
             'arch': 'x86_64',
             'payloadhash': '1234567890'}

PYTHON_3_6_7 = {'id': '7',
                'name': 'python',
                'epoch': '3',
                'version': '6',
                'release': '7.el7',
                'arch': 'x86_64',
                'payloadhash': '1234567890'}

# ARCHIVE BLOBS
IMAGE1 = {'id': 1,
          'checksum': '1234567890',
          'filename': 'image1.tar.gz',
          'buildroot_id': '1',
          'extra': {'image': {'arch': 'x86_64'}}}

IMAGE2 = {'id': 2,
          'checksum': '0987654321',
          'filename': 'image2.tar.gz',
          'buildroot_id': '2',
          'extra': {'image': {'arch': 'ppc64le'}}}


def read_metadata_test_data(self, FILE):
    if FILE == base.Analyzer.MESSAGE_FILE:
        return {'info': {'build_id': 759153}}
    if FILE == base.Analyzer.BUILD_FILE:
        return {'id': 759153,
                'source': "git://pkgs.devel.redhat.com/containers/virt-api#e9614e8eed02befd8ed021fe9591f84534221425",
                'name': "virt-api-container",
                'version': "1.2",
                'release': "4"}
    if FILE == base.Analyzer.TASK_FILE:
        return {'method': 'buildContainer'}
    if FILE == base.Analyzer.RPM_FILE:
        return [VIM_1_2_3, SSH_9_8_7]
    if FILE == base.Analyzer.ARCHIVE_FILE:
        return [IMAGE1, IMAGE2]
    if FILE == base.Analyzer.IMAGE_RPM_FILE:
        return {'1': [NETWORKMANAGER_5_6_7_X86],
                '2': [NETWORKMANAGER_5_6_7_PPC]}
    if FILE == base.Analyzer.BUILDROOT_FILE:
        return {'1': [GCC_2_3_4],
                '2': [PYTHON_3_6_7]}
    raise Exception("Unexpected file being read, mock it out! %s", FILE)


@mock.patch('assayist.processor.base.Analyzer.read_metadata_file', new=read_metadata_test_data)
def test_construct_rpm():
    """Test the basic function of the construct_rpm function."""
    analyzer = main_analyzer.MainAnalyzer()
    artifact = analyzer.get_or_create_rpm_artifact_from_hash(VIM_1_2_3)

    assert 'vim-1:2-3.el7' == artifact.filename
    assert VIM_1_2_3['payloadhash'] == artifact.checksum
    assert 'rpm-1' == artifact.archive_id
    assert VIM_1_2_3['arch'] == artifact.architecture

    # assert that we correctly treat a null epoch as 0
    artifact = analyzer.get_or_create_rpm_artifact_from_hash(VIM_2_3)
    assert 'vim-0:2-3.el7' == artifact.filename


@mock.patch('assayist.processor.base.Analyzer.read_metadata_file', new=read_metadata_test_data)
def test_read_and_save_buildroots():
    """
    Test the basic function of the build_and_save_buildroots function.
    The links to other artifacts won't exist yet, but the buildroot artifacts themselves should exist.
    """
    analyzer = main_analyzer.MainAnalyzer()
    analyzer.read_and_save_buildroots()

    assert Artifact.nodes.get(filename='gcc-2:3-4.el7')
    assert Artifact.nodes.get(filename='python-3:6-7.el7')
