# SPDX-License-Identifier: GPL-3.0+

import neomodel


def set_connection(neo4j_url):  # pragma: no cover
    """
    Set the Neo4j connection string.

    :param str neo4j_url: the Neo4j connection string to configure neomodel with
    """
    neomodel.db.set_connection(neo4j_url)
