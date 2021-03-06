#! /usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0+

import argparse
import logging
import os
import sys

from assayist.processor import utils
from assayist.processor.base import Analyzer
from assayist.processor.error import (
    BuildSourceNotFound, BuildTypeNotSupported, BuildInvalidState, BuildTypeNotFound,
)

# Always set the logging to INFO
log = logging.getLogger('assayist_processor')
log.setLevel(logging.INFO)
# Make the log statements look like print statements on the root log handler
logging.getLogger().handlers[0].setFormatter(logging.Formatter('%(message)s'))

parser = argparse.ArgumentParser(
    description='Download the artifacts associated with a build and unpack them')
parser.add_argument('build_identifier', type=str, help=('The Koji build identifer (ID or NVR)'))
parser.add_argument('--output-dir', type=str,
                    help='The path stored the downloaded and unpacked build')
args = parser.parse_args()

# If it's a build ID, we want it typed as an integer. If it's an NVR, then keep it as a string.
try:
    build_identifier = int(args.build_identifier)
except ValueError:
    build_identifier = args.build_identifier

output_dir = args.output_dir or '.'

output_metadata_dir = os.path.join(output_dir, Analyzer.METADATA_DIR)
output_files_dir = os.path.join(output_dir, Analyzer.FILES_DIR)
output_source_dir = os.path.join(output_dir, Analyzer.SOURCE_DIR)
unpacked_archives_dir = os.path.join(output_dir, Analyzer.UNPACKED_ARCHIVES_DIR)

for directory in (output_metadata_dir, output_files_dir, unpacked_archives_dir, output_source_dir):
    if not os.path.isdir(directory):
        os.mkdir(directory)

try:
    build_info = utils.download_build_data(build_identifier, output_metadata_dir)
except (BuildSourceNotFound, BuildInvalidState, BuildTypeNotFound) as exc:
    print(exc, file=sys.stderr)
    # If the build's source or type was not found, or the build is not in a valid state,
    # exit the script with an exit code of 3. Then the runner of the script can determine what
    # to do from here.
    sys.exit(3)
except BuildTypeNotSupported as exc:
    print(exc)
    # If the build type is not supported, exit early so that we don't download a lot of
    # unnecessary data. Exit with 0 so that minimal analysis (creating a Build node) continues.
    sys.exit(0)

artifacts = utils.download_build(build_info, output_files_dir)
utils.download_source(build_info, output_source_dir)
utils.unpack_artifacts(artifacts, unpacked_archives_dir)

log.info(f'See the downloaded brew metadata at {output_metadata_dir}')
log.info(f'See the downloaded archives at {output_files_dir}')
log.info(f'See the downloaded source at {output_source_dir}')
log.info(f'See the unpacked archives at {unpacked_archives_dir}')
