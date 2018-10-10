# SPDX-License-Identifier: GPL-3.0+

import neomodel

from assayist.common.models.content import Build
from assayist.client.error import NotFound


def set_connection(neo4j_url):  # pragma: no cover
    """
    Set the Neo4j connection string.

    :param str neo4j_url: the Neo4j connection string to configure neomodel with
    """
    neomodel.db.set_connection(neo4j_url)


def get_container_by_component(component_name, component_version):
    """Query for builds by component name and version.

    Finds builds that produced container images which include or embed a component with the
    specified name and version, and any version preceding that version.

    :param str component_name: name of the component to query for
    :param str component_version: version of the component to query for
    :return: list of builds IDs
    :rtype: list
    """
    query = """
        MATCH (c:Component {{canonical_name: '{name}'}}) <-[:SOURCE_FOR]-
              (:SourceLocation {{canonical_version: '{version}'}}) <-[:UPSTREAM|EMBEDS*0..]-
              (target_sl:SourceLocation) <-[:BUILT_FROM]- (build:Build)
        OPTIONAL MATCH (build) -[:PRODUCED]-> (:Artifact) <-[:EMBEDS*0..]-
                       (:Artifact) <-[:PRODUCED]- (container_build:Build {{type: 'container'}})
        OPTIONAL MATCH (target_sl) <-[:BUILT_FROM]- (cf_build:Build {{type: 'container'}})
        RETURN container_build, cf_build
    """.format(name=component_name, version=component_version)

    results, _ = neomodel.db.cypher_query(query)

    build_ids = set()
    for result in results:
        for node in result:
            if node:
                build_ids.add(node['id'])

    return build_ids


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
