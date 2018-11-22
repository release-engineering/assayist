#! /usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0+

import argparse

from neomodel import db

from assayist.common.models.content import Build
from assayist.processor.configuration import config
from assayist.processor.base import Analyzer

parser = argparse.ArgumentParser(description='Return a list of stubbed builds')
args = parser.parse_args()

db.set_connection(config.DATABASE_URL)
stubbed_builds = Build.nodes.has(source_location=False).filter(
    type___in=Analyzer.SUPPORTED_BUILD_TYPES)

for build in stubbed_builds:
    print(build.id_)
