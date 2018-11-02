# SPDX-License-Identifier: GPL-3.0+

import mock
import pytest

from assayist.processor.container_analyzer import ContainerAnalyzer
from tests.factories import BuildFactory, ArtifactFactory
from tests.processor.test_main import IMAGE1, IMAGE2


class TestContainerAnalyzerRun:
    """Test container analysis against a common build."""

    @pytest.fixture(scope='function', autouse=True)
    def setup_build_with_artifacts(self):
        """Create a container build with two archive artifacts with different architectures."""
        build = BuildFactory.create(id_=774500, type_='container')

        artifacts = []
        for arch in ('x86_64', 's390x', 'ppc64le'):
            artifacts.append(
                ArtifactFactory.create(type_='container', architecture=arch)
            )

        for artifact in artifacts:
            artifact.build.connect(build)

    @mock.patch('assayist.processor.base.Analyzer.read_metadata_file')
    @mock.patch('assayist.processor.container_analyzer.ContainerAnalyzer._create_or_update_parent')
    def test_run_no_parent(self, mock_c_o_u_parent_build, mock_read_md_file):
        """Test the ContainerAnalyzer.run function against a base image with no parent builds."""
        # Minimal set of Brew build info metadata of a base image container (has no parents)
        mock_read_md_file.return_value = {
            'package_name': 'rhel-server-container',
            'id': 774500,
            'extra': {
                'container_koji_task_id': 18568951,
                'image': {
                    'parent_image_builds': {},
                },
            },
        }

        analyzer = ContainerAnalyzer()
        analyzer.run()

        assert mock_c_o_u_parent_build.call_count == 0

    @mock.patch('assayist.processor.base.Analyzer.read_metadata_file')
    @mock.patch('assayist.processor.container_analyzer.ContainerAnalyzer._create_or_update_parent')
    def test_run_one_parent(self, mock_c_o_u_parent_build, mock_read_md_file):
        """Test the ContainerAnalyzer.run function against an image with one parent build."""
        # Minimal set of Brew build info metadata of a container build that has one parent build
        mock_read_md_file.return_value = {
            'package_name': 'openshift-enterprise-base-container',
            'id': 774500,  # Real ID: 787425
            'extra': {
                'container_koji_task_id': 18903380,
                'image': {
                    'parent_build_id': 742050,
                    'parent_image_builds': {
                        'rhel7:7-released': {
                            'id': 742050,
                            'nvr': 'rhel-server-container-7.5-424',
                        },
                    },
                },
            },
        }

        arch_to_artifacts = {arch: ArtifactFactory.create(type_='container', architecture=arch)
                             for arch in ('x86_64', 's390x', 'ppc64le')}
        mock_c_o_u_parent_build.return_value = arch_to_artifacts

        analyzer = ContainerAnalyzer()
        analyzer.run()

        assert mock_c_o_u_parent_build.call_count == 1

        # Check that all parent artifacts are linked to their respective artifacts by architecture
        for arch, parent_artifact in arch_to_artifacts.items():
            assert parent_artifact.artifacts_embedded_in.get().architecture == arch

    @mock.patch('assayist.processor.base.Analyzer.read_metadata_file')
    @mock.patch('assayist.processor.container_analyzer.ContainerAnalyzer._create_or_update_parent')
    def test_run_multiple_parents(self, mock_c_o_u_parent_build, mock_read_md_file):
        """Test the ContainerAnalyzer.run function against an image with multiple parent builds."""
        # Minimal set of Brew build info metadata of a container build with multiple parent builds
        mock_read_md_file.return_value = {
            'package_name': 'openshift-enterprise-console-container',
            'id': 774500,  # Real ID: 787432
            'extra': {
                'container_koji_task_id': 18903872,
                'image': {
                    'parent_build_id': 787425,
                    'parent_image_builds': {
                        'openshift/golang-builder:1.10': {
                            'id': 780769,
                            'nvr': 'openshift-golang-builder-container-1.10-1.10.3.6',
                        },
                        'openshift3/ose-base:v3.11.31.20181023.223156': {
                            'id': 787425,
                            'nvr': 'openshift-enterprise-base-container-v3.11.31-1',
                        },
                        'rhscl/nodejs-8-rhel7:1': {
                            'id': 771613,
                            'nvr': 'rh-nodejs8-container-1-30',
                        },
                    },
                },
            },
        }

        arch_to_embedded_artifacts = {
            arch: ArtifactFactory.create(type_='container', architecture=arch)
            for arch in ('x86_64', 's390x', 'ppc64le')
        }

        arch_to_buildroot_artifacts_1 = {
            arch: ArtifactFactory.create(type_='container', architecture=arch)
            for arch in ('x86_64', 's390x', 'ppc64le')
        }

        arch_to_buildroot_artifacts_2 = {
            arch: ArtifactFactory.create(type_='container', architecture=arch)
            for arch in ('x86_64', 's390x', 'ppc64le')
        }

        mock_c_o_u_parent_build.side_effect = [
            arch_to_embedded_artifacts,
            arch_to_buildroot_artifacts_1,
            arch_to_buildroot_artifacts_2,
        ]

        analyzer = ContainerAnalyzer()
        analyzer.run()

        assert mock_c_o_u_parent_build.call_count == 3

        # Check that all parent artifacts are embedded in their respective artifacts by architecture
        for arch, parent_artifact in arch_to_embedded_artifacts.items():
            assert parent_artifact.artifacts_embedded_in.get().architecture == arch

        # Check that all parent artifacts are embedded as buildroot artifacts to their respective
        # child artifacts.
        for arch, parent_artifact in arch_to_buildroot_artifacts_1.items():
            assert parent_artifact.artifacts_in_buildroot_for.get().architecture == arch

        for arch, parent_artifact in arch_to_buildroot_artifacts_2.items():
            assert parent_artifact.artifacts_in_buildroot_for.get().architecture == arch


def test_create_or_update_parent_build_new():
    """Test the ContainerAnalyzer._create_or_update_parent function for a new parent build."""
    m_koji = mock.Mock()
    m_koji.listArchives.return_value = [IMAGE1, IMAGE2]

    analyzer = ContainerAnalyzer()
    analyzer._koji_session = m_koji
    arch_to_artifact_object = analyzer._create_or_update_parent(123456)

    assert arch_to_artifact_object

    image1_arch = IMAGE1['extra']['image']['arch']
    assert arch_to_artifact_object[image1_arch].archive_id == IMAGE1['id']

    image2_arch = IMAGE2['extra']['image']['arch']
    assert arch_to_artifact_object[image2_arch].archive_id == IMAGE2['id']
