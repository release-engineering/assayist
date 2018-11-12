#! /usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0+

import argparse

from assayist.processor.container_analyzer import ContainerAnalyzer
from assayist.processor.container_go_analyzer import ContainerGoAnalyzer
from assayist.processor.container_rpm_analyzer import ContainerRPMAnalyzer
from assayist.processor.loose_rpm_analyzer import LooseRpmAnalyzer
from assayist.processor.main_analyzer import MainAnalyzer
from assayist.processor.post_analyzer import PostAnalyzer

parser = argparse.ArgumentParser(description='Run the Assayist analyzers on a Koji build')
parser.add_argument('--input-dir', type=str,
                    help='The directory containing the "metadata" directory')
args = parser.parse_args()

input_dir = args.input_dir or '.'

print('Running the main analyzer...')
MainAnalyzer(input_dir).main()
print('Running the container analyzer...')
ContainerAnalyzer(input_dir).main()
print('Running the container RPM analyzer...')
ContainerRPMAnalyzer(input_dir).main()
print('Running the container Go analyzer...')
ContainerGoAnalyzer(input_dir).main()
print('Running the loose RPM analyzer...')
LooseRpmAnalyzer(input_dir).main()
print('Running the post-analyzer...')
PostAnalyzer(input_dir).main()
