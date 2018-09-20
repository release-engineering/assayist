# SPDX-License-Identifier: GPL-3.0+

from abc import ABC, abstractmethod
import json
from neomodel import config, db
import os

class Analyzer(ABC):
    """ Base Abstract class that analyzers will inherit from. """
    METADATA_DIR = '/metadata/'
    MESSAGE_FILE = METADATA_DIR + 'message.json'
    BUILD_FILE = METADATA_DIR + 'buildinfo.json'
    TASK_FILE = METADATA_DIR + 'taskinfo.json'
    RPM_FILE = METADATA_DIR + 'rpms.json'
    ARCHIVE_FILE = METADATA_DIR + 'archives.json'
    IMAGE_RPM_FILE = METADATA_DIR + 'image-rpms.json'
    BUILDROOT_FILE = METADATA_DIR + 'buildroot-components.json'

    @classmethod
    def main(cls):
        """ Call this to run the analyzer. """
        # Pull Neo connection url from env variable, default to local
        config.DATABASE_URL = os.environ.get('NEO4J_BOLT_URL', 'bolt://neo4j:neo4j@localhost:7687')
        config.AUTO_INSTALL_LABELS = True
        # run the analyzer in a transaction
        db.begin()
        try:
            cls.run()
            db.commit()
        except Exception as e:
            db.rollback()
            raise


    @abstractmethod
    def run(self):
        """ Implement anlyzer code here in your subclass. """


    def read_metadata_file(self, FILE):
        """ Read and return the specified json metadata file or an empty dict. """
        if os.path.isfile(FILE):
            with open(FILE, 'r') as f:
                return json.load(f)
        else:
            return {}
