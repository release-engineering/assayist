# SPDX-License-Identifier: GPL-3.0+

import neomodel

from assayist.common.models.content import Build
from assayist.client.error import NotFound


def set_connection(neo4j_url):
    """
    Set the Neo4j connection string.

    :param str neo4j_url: the Neo4j connection string to configure neomodel with
    """
    neomodel.db.set_connection(neo4j_url)


def get_container_content_sources(build_id):
    """
    Get the sources used by the content in the container image.

    :param int build_id: the Koji build's ID
    :return: a list of source URLs
    :rtype: list
    """
    build = Build.nodes.get_or_none(id_=str(build_id))
    if not build:
        raise NotFound('The requested build does not exist in the database')

    # Bypass neomodel and use cypher directly for better performance
    internal_query = """
        MATCH (:Build {{id: '{0}'}})-[:PRODUCED]->(:Artifact)-[:EMBEDS]-(:Artifact)
            <-[:PRODUCED]-(:Build)-[:BUILT_FROM]->(internal:SourceLocation)
        OPTIONAL MATCH (internal)-[:UPSTREAM]->(upstream:SourceLocation)
        RETURN internal.url, upstream.url;
    """.format(build_id)
    results, _ = neomodel.db.cypher_query(internal_query)
    internal_urls = []
    upstream_urls = []
    for result in results:
        internal_urls.append(result[0])
        upstream_urls.append(result[1])
    return {
        'internal_urls': internal_urls,
        'upstream_urls': upstream_urls
    }
