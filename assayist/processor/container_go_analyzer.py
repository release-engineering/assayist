# SPDX-License-Identifier: GPL-3.0+

from glob import glob
import os
import subprocess
import tempfile

from dockerfile_parse import DockerfileParser

from assayist.common.models import content, source
from assayist.processor.base import Analyzer
from assayist.processor.utils import assert_command, unpack_zip, unpack_tar
from assayist.processor.logging import log
from assayist.processor.error import AnalysisFailure


class ContainerGoAnalyzer(Analyzer):
    """Analyze the Go executables in a container image layer."""

    # goversion executable path.
    GOVERSION = 'goversion'

    # Backvendor executable path.
    BACKVENDOR = 'backvendor'

    # Output format template for backvendor.
    # The module name will be followed by fields in this format.
    BACKVENDOR_TEMPLATE = '\t{{.Ver}}\t{{.Repo}}\t{{.Rev}}'

    # Types of identified source modules
    UPSTREAM = 'upstream'
    VENDORED = 'embedded_source_locations'

    # Files expected to be local and not upstream.
    DIST_GIT_EXCLUDES = [
        '.git*',
        'Makefile',
        'sources',
        'Dockerfile*',
        'additional-tags',
        'content_sets.yml',
        'container.yaml',
        '.oit',
        'public',
        'scripts',
    ]

    def run(self):
        """
        Start the container Go analyzer.

        :raises AnalysisFailure: if the analyzer completed with errors
        """
        # Check we have access to the executables we need.
        assert_command(self.BACKVENDOR)
        assert_command(self.GOVERSION)

        build_info = self.read_metadata_file(self.BUILD_FILE)
        build_id = build_info['id']

        if build_info['type'] != self.CONTAINER_BUILD_TYPE:
            log.info(f'Skipping build {build_id} because the build is not a container')
            return

        # This container's build is assumed to exist since it is
        # created by the main analyzer.
        build = content.Build.nodes.get(id_=build_id)
        source_locations = build.source_location.all()
        try:
            source_location = source_locations[0]
        except IndexError:
            msg = f'Missing source location for container build {build_id}'
            log.error(msg)
            raise AnalysisFailure(msg)

        srcdir = os.path.join(self.input_dir, self.SOURCE_DIR)

        # Store the failure messages so they can be returned in an AnalysisFailure exception
        failures = []
        failed_src_exc_msg = 'Failed while processing the source in "{}"'
        failed_src_msg = 'Failed while processing the source in "{}" with "{}"'

        # First process the source code that's directly available in
        # the dist-git repository.
        try:
            self._process_git_source(source_location, srcdir)
        except RuntimeError as error:
            log.exception(failed_src_exc_msg.format(srcdir))
            failures.append(failed_src_msg.format(srcdir, error))

        # Next process source code from archives (from 'rhpkg sources').
        # Look for tar archives and zip archives.
        tar_archives = glob(os.path.join(srcdir, '*.tar.*'))
        zip_archives = glob(os.path.join(srcdir, '*.zip'))
        archives = [(unpack_tar, archive) for archive in tar_archives]
        archives += [(unpack_zip, archive) for archive in zip_archives]
        for unpack, archive in archives:
            with tempfile.TemporaryDirectory() as subsrc:
                unpack(archive, subsrc)
                try:
                    self._process_source_code(source_location, subsrc)
                except RuntimeError as error:
                    log.exception(failed_src_exc_msg.format(srcdir))
                    failures.append(failed_src_msg.format(subsrc, error))

        # Now claim all the Go executables.
        self._claim_go_executables()

        if failures:
            raise AnalysisFailure('GoAnalyzer completed with the following error(s): \n  {}'
                                  .format("\n  ".join(failures)))

    def _process_git_source(self, source_location, srcdir):
        """Run backvendor on the dist-git repository source code.

        Exclude files known to be specific to the git repository and
        not expected to be upstream.

        Parse the output and update the database accordingly.

        :param SourceLocation source_location: local source code DB node
        :param str srcdir: path to source code to examine
        """
        # In case we need to provide an import path, see if there is
        # an io.openshift.source-repo-url label in the Dockerfile to help
        # us guess one.
        import_path_from_source_url = self._get_import_path_override(srcdir)

        # If we have a reasonable guess, see if we will need to use it.
        import_path = None
        if (import_path_from_source_url and
                not self._import_paths_known(srcdir,
                                             excludes=self.DIST_GIT_EXCLUDES)):
            import_path = import_path_from_source_url

        self._process_source_code(source_location, srcdir,
                                  import_path=import_path,
                                  excludes=self.DIST_GIT_EXCLUDES)

    def _get_import_path_override(self, srcdir):
        """Look inside the Dockerfile for a named label.

        :param srcdir: path to source code to examine
        :return: import path override, or None
        :rtype str/None:
        """
        label = 'io.openshift.source-repo-url'
        try:
            df = DockerfileParser(srcdir, cache_content=True)
        except IOError:
            log.exception('Unable to read Dockerfile')
            return None

        try:
            repo = df.labels[label]
        except KeyError:
            log.debug(f'No {label} label in Dockerfile')
            return None
        except:  # noqa:E722
            log.exception('Failed to process Dockerfile; ignoring')
            return None

        # Convert it to an import path by stripping off the scheme.
        (_, _, import_path) = repo.rpartition('://')
        if not import_path:
            return None

        return import_path

    def _run_backvendor(self, srcdir, import_path=None, excludes=None,
                        opts=None):
        """Run backvendor and returns its output.

        :param srcdir: path to source code to examine
        :param str/None import_path: import path for top-level module
        :param list/None excludes: list of globs to ignore
        :param list/None opts: any additional parameters
        :return: output from command
        :rtype: (str, str)
        """
        with tempfile.NamedTemporaryFile(mode='wt') as excludes_file:
            options = ['-debug', '-x', '-template', self.BACKVENDOR_TEMPLATE]
            if import_path:
                options += ['-importpath', import_path]

            if excludes:
                excludes_file.write(''.join('%s\n' % e for e in excludes))
                excludes_file.flush()
                options += ['-exclude-from', excludes_file.name]

            if opts:
                options += opts

            cmd = [self.BACKVENDOR] + options + [srcdir]
            log.info(f'Running {cmd}')
            bv = subprocess.Popen(cmd, universal_newlines=True,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)

            (stdout, stderr) = bv.communicate()

        returncode = bv.wait()
        if returncode:
            raise RuntimeError(f'The command "{" ".join(cmd)}" failed with: {stderr}')

        return stdout, stderr

    def _import_paths_known(self, srcdir, excludes=None):
        """Run backvendor to ask it if is has all the information it needs.

        :param srcdir: path to source code to examine
        :param list/None excludes: list of globs to ignore
        :return: whether backvendor has enough information
        :rtype: bool
        """
        try:
            self._run_backvendor(srcdir, excludes=excludes, opts=['-only-importpath'])
        except RuntimeError:
            return False

        return True

    def _process_source_code(self, source_location, srcdir, import_path=None,
                             excludes=None):
        """Run backvendor on the source code and parse its output.

        :param SourceLocation source_location: local source code DB node
        :param str srcdir: path to source code to examine
        :param str/None import_path: import path for top-level module
        :param list/None excludes: list of globs to ignore
        """
        stdout, stderr = self._run_backvendor(srcdir, import_path=import_path,
                                              excludes=excludes)

        # Parse the output from backvendor.
        for line in stdout.splitlines():
            fields = line.split('\t')
            if len(fields) != 4:
                log.error(f'invalid backvendor output: {line}')
                continue

            mod, ver, repo, rev = fields

            # The module field begins with an asterisk for a top-level module
            srctype = self.VENDORED
            if mod.startswith('*'):
                mod = mod[1:]
                srctype = self.UPSTREAM

            self._process_go_module(source_location, srctype,
                                    mod, ver, repo, rev)

    def _process_go_module(self, source_location, srctype,
                           mod, ver, repo, rev):
        """Update the database with the information from backvendor.

        :param SourceLocation source_location: local source location DB node
        :param str srctype: either self.UPSTREAM or self.VENDORED
        :param str mod: module name
        :param str ver: version
        :param str repo: repository URL
        :param str rev: vcs revision
        """
        namespace, name = mod.rsplit('/', 1)  # There must be at least one '/'
        component = source.Component.get_or_create_singleton(namespace, name, 'golang')
        upstream = self.create_or_update_source_location("#".join([repo, rev]),
                                                         component,
                                                         ver)
        relationship = getattr(source_location, srctype)
        relationship.connect(upstream)

        if srctype == self.UPSTREAM:
            # Connect the component to the local source location it is
            # the upstream for.
            component.source_locations.connect(source_location)

    def _claim_go_executables(self):
        """Claim executables identified by goversion."""
        not_container_msg = 'Skipping archive {0} since it\'s not a container image'
        archives = self.read_metadata_file(self.ARCHIVE_FILE)
        for index, archive in enumerate(archives):
            if not self.is_container_archive(archive):
                log.debug(not_container_msg.format(archive['id']))
                continue

            layer_dir = os.path.join(self.input_dir,
                                     self.UNPACKED_CONTAINER_LAYER_DIR,
                                     archive['filename'])

            cmd = [self.GOVERSION, '.']
            log.info(f'Running {cmd}')
            gv = subprocess.Popen(cmd, cwd=layer_dir, universal_newlines=True,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
            (stdout, stderr) = gv.communicate()
            returncode = gv.wait()
            if returncode:
                raise RuntimeError(f'The command "{" ".join(cmd)}" failed with: {stderr}')

            for line in stdout.splitlines():
                path, _ = line.split(' ', 1)
                log.info(f'(archive {index+1}/{len(archives)}) Claiming {path}')
                self.claim_container_file(archive, path)
