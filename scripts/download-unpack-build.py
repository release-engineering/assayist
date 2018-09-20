# SPDX-License-Identifier: GPL-3.0+

import argparse
import logging
import os

from assayist.processor.utils import download_build, unpack_artifacts


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

output_files_dir = os.path.join(output_dir, 'output_files')
unpacked_archives_dir = os.path.join(output_dir, 'unpacked_archives')
for directory in (output_files_dir, unpacked_archives_dir):
    if not os.path.isdir(directory):
        os.mkdir(directory)
artifacts = download_build(build_identifier, output_files_dir)
unpack_artifacts(artifacts, unpacked_archives_dir)
log.info(f'See the downloaded archives at {output_files_dir}')
log.info(f'See the unpacked archives at {unpacked_archives_dir}')
