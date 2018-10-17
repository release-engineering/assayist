# SPDX-License-Identifier: GPL-3.0+

import neomodel

from assayist.common.models.content import Artifact, Build
from assayist.common.models.source import Component, SourceLocation
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


def get_source_components_for_build(build_id):
    """
    Get source code components used in a build.

    In more detail:
    Get the canonical names of
    the sources ultimately used for
    artifacts ultimately embedded in
    the artifact from a build.

    For example: for a container image build, get the names of:
    * Upstream projects for RPMs installed in the images
    * Go packages used to build executables in the images
    etc

    The canonical names include versions where available.

    This function is implemented using two DB queries. The first
    establishes the artifacts our query relates to, as well any
    relationships between them. The second finds the information
    needed to establish source code versions relating to those
    artifacts.

    :param int build_id: the Koji build's ID
    :return: a tree of artifacts and the source code components
    :rtype: dict
    """
    build = Build.nodes.get_or_none(id_=str(build_id))
    if not build:
        raise NotFound('The requested build does not exist in the database')

    query = """
    // Find artifacts which (or artifacts which embed artifacts which)...
    //
    // (Note: "*0.." means zero or more edges; if zero edges, 'a' is the
    // artifact directly produced by the build.)
    MATCH (a:Artifact) <-[e:EMBEDS*0..]- (:Artifact)

    // Were produced by the build
            <-[:PRODUCED]- (:Build {{id: {0} }})

    // Return the artifacts and relationships
    RETURN a, e
    """.format(repr(str(build_id)))

    results, _ = neomodel.db.cypher_query(query)
    artifact_dbids = set()
    artifacts_by_id = {}
    for artifact in [Artifact.inflate(a) for a, _ in results]:
        artifacts_by_id[(artifact.type_, artifact.archive_id)] = {
            'artifact': {key: getattr(artifact, key)
                         for key in ('architecture', 'filename')}
        }
        artifact_dbids.add(artifact.id)

    embedded_artifacts = set()  # needed when we build a tree later
    for _, edges in results:
        for edge in edges:
            embeds, embedded = [Artifact.inflate(node)
                                for node in edge.nodes]
            by_id = artifacts_by_id[(embeds.type_, embeds.archive_id)]
            embeds_list = by_id.setdefault('embeds_ids', set())
            index = (embedded.type_, embedded.archive_id)
            embeds_list.add(index)
            embedded_artifacts.add(index)

    query = """
    // Find the artifacts
    MATCH (a:Artifact) WHERE id(a) IN [{0}]

    // Find the builds that produced all of those
    // (this includes the original build)
    MATCH (a) <-[:PRODUCED]- (:Build)

    // Find the source each was built from
            -[:BUILT_FROM]-> (:SourceLocation)

    // Include upstream or vendored source locations
    //
    // Note: this is 0 or more relationships, each of which
    // may be either UPSTREAM or EMBEDS
            -[:UPSTREAM|EMBEDS*0..]-> (sl:SourceLocation)

    // Find the components these locations are source for
            -[:SOURCE_FOR]-> (c:Component)

    // Only include source locations with no further upstream
    WHERE NOT (sl) -[:UPSTREAM]-> (:SourceLocation)

    RETURN a, sl, c
    """.format(','.join(repr(dbid) for dbid in artifact_dbids))

    results, _ = neomodel.db.cypher_query(query)

    for a, sl, c in results:
        artifact = Artifact.inflate(a)
        sourceloc = SourceLocation.inflate(sl)
        component = Component.inflate(c)

        metadata = artifacts_by_id[(artifact.type_, artifact.archive_id)]
        sources = metadata.setdefault('sources', [])
        pieces = {}
        for piece in ('type', 'namespace', 'name'):
            pieces[piece] = getattr(component, 'canonical_{}'.format(piece))

        pieces['version'] = sourceloc.canonical_version
        pieces['qualifiers'] = {'download_url': sourceloc.url}
        sources.append(pieces)

    # Build a tree of artifacts
    artifacts = {}
    toplevel = [key for key, value in artifacts_by_id.items()
                if key not in embedded_artifacts]

    def construct(aid):
        a = artifacts_by_id[aid]
        try:
            embeds_ids = a.pop('embeds_ids')
        except KeyError:
            return a

        a['embeds'] = {}
        for embedded_id in embeds_ids:
            a['embeds'][embedded_id] = construct(embedded_id)

        return a

    for aid in toplevel:
        artifacts[aid] = construct(aid)

    return artifacts
