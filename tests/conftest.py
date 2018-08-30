# SPDX-License-Identifier: GPL-3.0+

import os

import pytest
from neomodel import config as neomodel_config, db as neo4j_db

neomodel_config.DATABASE_URL = os.environ.get('NEO4J_BOLT_URL', 'bolt://neo4j:neo4j@localhost:7687')
neomodel_config.AUTO_INSTALL_LABELS = True


@pytest.fixture(autouse=True)
def run_before_tests():
    """Pytest fixture that prepares the environment before each test."""
    # Reinitialize Neo4j before each test
    neo4j_db.cypher_query('MATCH (a) DETACH DELETE a')
