#! /usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0+

import argparse

from assayist.processor.main_analyzer import MainAnalyzer
from assayist.processor.container_rpm_analyzer import ContainerRPMAnalyzer

parser = argparse.ArgumentParser(description='Run the Assayist analyzers on a Koji build')
parser.add_argument('--input-dir', type=str,
                    help='The directory containing the "metadata" directory')
args = parser.parse_args()

input_dir = args.input_dir or '.'

print('Running the main analyzer...')
MainAnalyzer(input_dir).main()
print('Running the container RPM analyzer...')
ContainerRPMAnalyzer(input_dir).main()
