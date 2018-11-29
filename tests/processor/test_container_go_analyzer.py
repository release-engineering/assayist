# SPDX-License-Identifier: GPL-3.0+

import mock
import pytest
from textwrap import dedent

from assayist.processor.container_go_analyzer import ContainerGoAnalyzer
from assayist.processor.error import AnalysisFailure
from tests.factories import (
    ArtifactFactory, BuildFactory, ModelFactory, SourceLocationFactory
)


MODULE = 'assayist.processor.container_go_analyzer'


class TestContainerGoAnalyzerRun:
    """Test container Go analysis."""

    @pytest.fixture(scope='function', autouse=True)
    def setup_build_with_source_and_artifacts(self):
        """Create a container build with archive artifacts with different architectures."""
        build = BuildFactory.create(id_=774500, type_='container')
        url = ModelFactory.generate_internal_git_url('foo', 'containers')
        source = SourceLocationFactory.create(url=url,
                                              canonical_version='1.0-1')
        build.source_location.connect(source)
        self.source_location = source
        for arch in ('x86_64', 's390x', 'ppc64le'):
            artifact = ArtifactFactory.create(type_='container',
                                              architecture=arch)
            artifact.build.connect(build)

    @mock.patch(MODULE + '.assert_command')
    @mock.patch('assayist.processor.base.Analyzer.read_metadata_file')
    @mock.patch(MODULE + '.ContainerGoAnalyzer._process_source_code')
    @mock.patch(MODULE + '.ContainerGoAnalyzer._claim_go_executables')
    def test_run(self, mock_claim_go_executables, mock_process_source_code,
                 mock_read_metadata_file, mock_assert_command):
        """Test the core logic in the run method."""
        mock_read_metadata_file.return_value = {
            'id': 774500,
            'type': 'buildContainer',
        }

        analyzer = ContainerGoAnalyzer()
        analyzer.run()
        mock_process_source_code.assert_called_once()
        mock_claim_go_executables.assert_called_once()

    @mock.patch(MODULE + '.assert_command')
    @mock.patch('assayist.processor.base.Analyzer.read_metadata_file')
    @mock.patch(MODULE + '.ContainerGoAnalyzer._process_source_code')
    @mock.patch(MODULE + '.ContainerGoAnalyzer._claim_go_executables')
    def test_run_with_source_code_error(self, mock_claim_go_executables, mock_process_source_code,
                                        mock_read_metadata_file, mock_assert_command):
        """Test the run method finishes and returns False when _process_source_code fails."""
        mock_read_metadata_file.return_value = {
            'id': 774500,
            'type': 'buildContainer',
        }
        mock_process_source_code.side_effect = RuntimeError('some Error')

        analyzer = ContainerGoAnalyzer()
        with pytest.raises(AnalysisFailure):
            analyzer.run()
        mock_process_source_code.assert_called_once()
        mock_claim_go_executables.assert_called_once()

    @pytest.mark.parametrize('content,expect', [
        (
            dedent("""\
            FROM scratch
            """).rstrip(),
            None,
        ),

        (
            dedent("""\
            FROM scratch
            LABEL io.openshift.source-repo-url=""
            """).rstrip(),
            None,
        ),

        (
            dedent("""\
            FROM scratch
            LABEL io.openshift.source-repo-url="https://example.com/example"
            """).rstrip(),
            'example.com/example',
        ),

        (
            dedent("""\
            FROM scratch
            LABEL io.openshift.source-repo-url="example.com/example"
            """).rstrip(),
            'example.com/example',
        ),
    ])
    def test_get_import_path_override(self, content, expect, tmpdir):
        """Test the _get_import_path_override method."""
        df = tmpdir.join('Dockerfile')
        df.write(content)

        # Call the method we're testing.
        analyzer = ContainerGoAnalyzer()
        override = analyzer._get_import_path_override(str(tmpdir))
        assert override == expect

    @pytest.mark.parametrize('import_path', (None, 'example.com/example'))
    @mock.patch(MODULE + '.ContainerGoAnalyzer._get_import_path_override')
    @mock.patch(MODULE + '.ContainerGoAnalyzer._import_paths_known')
    @mock.patch(MODULE + '.ContainerGoAnalyzer._process_source_code')
    def test_process_git_source(self, mock_process_source_code,
                                mock_import_paths_known,
                                mock_get_import_path_override,
                                import_path):
        """Test the _process_git_source method."""
        mock_get_import_path_override.return_value = import_path
        mock_import_paths_known.return_value = False

        source_location = object()
        srcdir = '/source'

        analyzer = ContainerGoAnalyzer()
        analyzer._process_git_source(source_location, srcdir)

        excludes = ContainerGoAnalyzer.DIST_GIT_EXCLUDES
        mock_get_import_path_override.assert_called_once_with(srcdir)
        if import_path:
            mock_import_paths_known.assert_called_once_with(srcdir,
                                                            excludes=excludes)
        else:
            mock_import_paths_known.assert_not_called()

        mock_process_source_code.assert_called_once_with(source_location, srcdir,
                                                         import_path=import_path,
                                                         excludes=excludes)

    @pytest.mark.parametrize('import_path', [None, 'example.com/example'])
    @pytest.mark.parametrize('excludes', [None, ['Dockerfile']])
    @pytest.mark.parametrize('opts', [None, ['-x']])
    @mock.patch(MODULE + '.subprocess.Popen')
    @mock.patch(MODULE + '.ContainerGoAnalyzer._process_go_module')
    def test_run_retrodep_err(self, mock_process_go_module, mock_popen,
                              import_path, excludes, opts):
        """Test a failure path in the _run_retrodep method."""
        attrs = {
            'communicate.return_value': ('', ''),
            'wait.return_value': 1,
        }
        process_mock = mock.Mock()
        process_mock.configure_mock(**attrs)
        mock_popen.return_value = process_mock
        analyzer = ContainerGoAnalyzer()
        with pytest.raises(RuntimeError):
            analyzer._run_retrodep('/source', import_path=import_path, excludes=excludes,
                                   opts=opts)

        mock_process_go_module.assert_not_called()

    @mock.patch(MODULE + '.subprocess.Popen')
    @mock.patch(MODULE + '.ContainerGoAnalyzer._process_go_module')
    def test_process_source_code_badfmt(self, mock_process_go_module, mock_popen):
        """Test a failure path in the _process_source_code method."""
        attrs = {
            'communicate.return_value': (
                '*github.com/foo/bar',  # deliberately incorrect format
                ''),
            'wait.return_value': 0,
        }
        process_mock = mock.Mock()
        process_mock.configure_mock(**attrs)
        mock_popen.return_value = process_mock
        analyzer = ContainerGoAnalyzer()
        analyzer._process_source_code(self.source_location, '/source')
        mock_process_go_module.assert_not_called()

    @pytest.mark.parametrize('excludes', [None, ["container.yaml"]])
    @mock.patch(MODULE + '.subprocess.Popen')
    @mock.patch(MODULE + '.ContainerGoAnalyzer._process_go_module')
    def test_process_source_code(self, mock_process_go_module, mock_popen,
                                 excludes):
        """Test the 'happy path' in the _process_source_code method."""
        modules = [
            {
                'type': 'upstream',
                'mod': '*github.com/foo/bar',
                'ver': 'v1.0.0',
                'repo': 'https://github.com/foo/bar',
                'rev': 'abc',
            },
            {
                'type': 'embedded_source_locations',
                'mod': 'example.com/example',
                'ver': 'v0.0.0-0.20181101152624-0123456789abcdef',
                'repo': 'https://github.com/example/example',
                'rev': '0123456789abcdef',
            },
        ]

        # Create the retrodep output.
        output = ''.join('{mod}\t{ver}\t{repo}\t{rev}\n'.format(**mod)
                         for mod in modules)

        # Set up a mock for retrodep.
        attrs = {
            'communicate.return_value': (
                # stdout
                output,

                # stderr
                ''),
            'wait.return_value': 0,
        }
        process_mock = mock.Mock()
        process_mock.configure_mock(**attrs)
        mock_popen.return_value = process_mock

        # Call the method we're testing.
        analyzer = ContainerGoAnalyzer()
        analyzer._process_source_code(self.source_location, '/source',
                                      excludes=excludes)

        # Check _process_go_module was called each time with the correct args.
        calls = []
        for mod in modules:
            call = mock.call(self.source_location, mod['type'],
                             mod['mod'].lstrip('*'),
                             mod['ver'], mod['repo'], mod['rev'])
            calls.append(call)

        mock_process_go_module.assert_has_calls(calls)

    def test_process_go_module(self):
        """Test the _process_go_module method."""
        modules = [
            {
                'type': 'upstream',
                'mod': 'github.com/foo/bar',
                'ver': 'v1.0.0',
                'repo': 'https://github.com/foo/bar',
                'rev': 'abc',

                'ns': 'github.com/foo',
                'name': 'bar',
                'url': 'https://github.com/foo/bar#abc',
            },
            {
                'type': 'embedded_source_locations',
                'mod': 'example.com/example',
                'ver': 'v0.0.0-0.20181101152624-0123456789abcdef',
                'repo': 'https://github.com/example/example',
                'rev': '0123456789abcdef',

                'ns': 'example.com',
                'name': 'example',
                'url': 'https://github.com/example/example#0123456789abcdef',
            },
            {
                'type': 'upstream',
                'mod': 'github.com/bar/foo',
                'ver': 'v2.0.0',
                'repo': 'https://github.com/bar/foo',
                'rev': 'def',

                'ns': 'github.com/bar',
                'name': 'foo',
                'url': 'https://github.com/bar/foo#def',
            },
        ]

        # Run the method several times.
        analyzer = ContainerGoAnalyzer()
        for mod in modules:
            analyzer._process_go_module(self.source_location,
                                        mod['type'],
                                        mod['mod'], mod['ver'],
                                        mod['repo'], mod['rev'])

        def check_source_location(node, mod):
            """Check the node against expected property values."""
            # Check the canonical version.
            assert node.canonical_version == mod['ver']

            # Check the namespace and name of the associated component.
            components = node.component.all()
            assert len(components) == 1
            component = components[0]
            assert (
                component.canonical_type,
                component.canonical_namespace,
                component.canonical_name,
            ) == (
                'golang',
                mod['ns'],
                mod['name'],
            )

        # Check every upstream we expect to be created is created.
        upstreams = self.source_location.upstream.all()
        assert len(upstreams) == 2

        for mod in [mod for mod in modules
                    if mod['type'] == 'upstream']:
            for upstream in upstreams:
                if upstream.url != mod['url']:
                    continue

                # This upstream node matches on URL. Check other attributes.
                check_source_location(upstream, mod)
                break
            else:
                assert False, f'{mod["url"]} not found'

        # Check every embedded source location we expect to be created
        # is created.
        vendored = self.source_location.embedded_source_locations.all()
        assert len(vendored) == 1
        for mod in [mod for mod in modules
                    if mod['type'] == 'embedded_source_locations']:
            for v in vendored:
                if v.url != mod['url']:
                    continue

                # This upstream node matches on URL. Check other attributes.
                check_source_location(v, mod)
                break
            else:
                assert False, f'{mod["url"]} not found'

    @mock.patch('assayist.processor.base.Analyzer.read_metadata_file')
    @mock.patch(MODULE + '.subprocess.Popen')
    @mock.patch(MODULE + '.Analyzer.claim_container_file')
    def test_claim_go_executables(self, mock_claim, mock_popen, mock_read_metadata_file):
        """Test the 'happy path' in the _claim_go_executables method."""
        # Provide the content of ARCHIVE_FILE.
        archives = [
            {
                'id': 3,
                'extra': {'image': {'arch': 'x86_64'}},
                'filename': 'docker-image-sha256-00003',
                'btype': 'image',
            },
            {
                'id': 4,
                'extra': {'image': {'arch': 's390x'}},
                'filename': 'docker-image-sha256-00004',
                'btype': 'image',
            },
            {
                'id': 5,
                'extra': {'image': {'arch': 'ppc64le'}},
                'filename': 'docker-image-sha256-00005',
                'btype': 'image',
            },
        ]
        mock_read_metadata_file.return_value = archives

        # Set up a mock for goversion.
        attrs = {
            'communicate.return_value': (
                # stdout
                dedent("""\
                a/b/c/foo go1.11
                a/b/c/bar go1.11
                d/e/f/foo go1.11
                d/e/f/bar go1.11
                bin/example go1.11
                """),

                # stderr
                ''),
            'wait.return_value': 0,
        }
        process_mock = mock.Mock()
        process_mock.configure_mock(**attrs)
        mock_popen.return_value = process_mock

        analyzer = ContainerGoAnalyzer()
        analyzer._claim_go_executables()

        # Check claim_container_file was called each time with the correct args.
        calls = []
        for archive in archives:
            for path in (
                    'a/b/c/foo',
                    'a/b/c/bar',
                    'd/e/f/foo',
                    'd/e/f/bar',
                    'bin/example',
            ):
                calls.append(mock.call(archive, path))

        assert mock_claim.call_count == len(calls)
        mock_claim.assert_has_calls(calls, any_order=True)
