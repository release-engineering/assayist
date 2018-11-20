#! /usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0+

import argparse
import sys

from assayist.processor.container_analyzer import ContainerAnalyzer
from assayist.processor.container_go_analyzer import ContainerGoAnalyzer
from assayist.processor.container_rpm_analyzer import ContainerRPMAnalyzer
from assayist.processor.loose_artifact_analyzer import LooseArtifactAnalyzer
from assayist.processor.main_analyzer import MainAnalyzer
from assayist.processor.post_analyzer import PostAnalyzer
from assayist.processor.error import AnalysisFailure


parser = argparse.ArgumentParser(description='Run the Assayist analyzers on a Koji build')
parser.add_argument('--input-dir', type=str,
                    help='The directory containing the "metadata" directory')
args = parser.parse_args()

input_dir = args.input_dir or '.'

analyzers = [MainAnalyzer, ContainerAnalyzer, ContainerRPMAnalyzer, ContainerGoAnalyzer,
             LooseArtifactAnalyzer, PostAnalyzer]
analyzer_failures = []

for analyzer in analyzers:
    print(f'Running {analyzer.__name__}...')
    try:
        analyzer(input_dir).main()
    except AnalysisFailure as error:
        # Don't continue if the main analyzer failed since other analyzers rely on it
        if analyzer == MainAnalyzer:
            print('MainAnalyzer failed with the following:\n{}'.format(error),
                  file=sys.stderr)
            sys.exit(3)

        analyzer_failures.append(str(error))

if analyzer_failures:
    print('The following were error(s) encountered during the analysis:\n{}'.format(
        '\n'.join(analyzer_failures)), file=sys.stderr)
    sys.exit(3)
