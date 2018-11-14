#! /usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0+

import argparse
from neomodel import db

from assayist.common.models.content import Build
from assayist.processor.configuration import config

parser = argparse.ArgumentParser(description='Return a list of stubbed builds')
args = parser.parse_args()

db.set_connection(config.DATABASE_URL)
stubbed_builds = Build.nodes.has(source_location=False).all()

for build in stubbed_builds:
    print(build.id_)
