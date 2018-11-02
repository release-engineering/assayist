#! /usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0+

import argparse

from assayist.processor.main_analyzer import MainAnalyzer

parser = argparse.ArgumentParser(description='Run the main analyzer')
parser.add_argument('--input-dir', type=str,
                    help='The directory containing the "metadata" directory')
args = parser.parse_args()

input_dir = args.input_dir or '.'

MainAnalyzer(input_dir).main()
