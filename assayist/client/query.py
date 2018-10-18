# SPDX-License-Identifier: GPL-3.0+

import collections

import neomodel

from assayist.common.models.content import Artifact, Build
from assayist.common.models.source import Component, SourceLocation
from assayist.client.error import NotFound, InvalidInput


def set_connection(neo4j_url):  # pragma: no cover
    """
    Set the Neo4j connection string.

    :param str neo4j_url: the Neo4j connection string to configure neomodel with
    """
    neomodel.db.set_connection(neo4j_url)


def get_container_by_component(name, type_, version):
    """Query for builds by component name and version.

    Finds builds that produced container images which include or embed a component with the
    specified name, type, and version.

    :param str name: the canonical name of the component
    :param str type_: the canonical type of the component
    :param str version: the canonical version of the component
    :return: list of builds IDs
    :rtype: list
    """
    query = """
        // Find a component and a sourcelocation with the specified name, type and version. These
        // can be emdedded in other sourcelocation that are used as a source for a build or directly
        // used for a build.
        MATCH (c:Component {{canonical_name: '{name}', canonical_type: '{type}'}}) <-[:SOURCE_FOR]-
              (version_sl:SourceLocation {{canonical_version: '{version}'}})
              <-[:UPSTREAM|EMBEDS*0..]- (target_sl:SourceLocation)
              <-[:BUILT_FROM]- (build:Build)

        // Find all container builds that embed an artifact produced by any of the previously
        // matched builds.
        OPTIONAL MATCH (build) -[:PRODUCED]-> (:Artifact) <-[:EMBEDS*0..]-
                       (:Artifact) <-[:PRODUCED]- (container_build:Build {{type: 'container'}})

        // Find all container builds that are directly built from any of the previously matched
        // sourcelocations.
        OPTIONAL MATCH (target_sl) <-[:BUILT_FROM]- (cf_build:Build {{type: 'container'}})

        // Return both types of builds.
        RETURN container_build, cf_build
    """.format(name=name, type=type_, version=version)

    results, _ = neomodel.db.cypher_query(query)

    build_ids = set()
    for result in results:
        for node in result:
            if node:
                build_ids.add(int(node['id']))

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


def get_current_and_previous_versions(name, type_, version):
    """
    Find the current and previous source locations.

    :param str name: the canonical name of the component
    :param str type_: the canonical type of the component
    :param str version: the canonical version of the source location
    :return: a dictionary of all the previous source locations and the current source location
    :rtype: dict
    """
    # TODO: Consider alternative names as well
    query = """
        MATCH (:Component {{canonical_name: '{name}', canonical_type: '{type}'}})
            <-[:SOURCE_FOR]-(:SourceLocation {{canonical_version: '{version}'}})
            -[:SUPERSEDES*0..]->(sl:SourceLocation)
        RETURN sl
    """.format(name=name, type=type_, version=version)
    results, _ = neomodel.db.cypher_query(query)
    rv = []
    for result in results:
        rv.append(dict(result[0]))
    return rv


def get_container_built_with_sources(source_locations):
    """
    Match container builds that used the input source locations to build the content in the image.

    This means any container that:
    * embeds artifacts that were built with artifacts built from the input and related source
      locations
    * was built with a container that embeds artifacts that were built with the input and related
      source locations

    :param list source_locations: a list of source location dictionaries to match against
    :return: a list of affected container build Koji IDs
    :rtype: list
    """
    if not source_locations or not isinstance(source_locations, collections.Iterable):
        raise InvalidInput('The input must be a list of source locations')

    # Get all the input source locations, then find the upstream or downstream source locations.
    # With that result, find all the source locations that embed the resulting source locations.
    # Then return the Neo4j IDs of the union of all the source locations in the query.
    query = """
    // First get all the input source locations
    MATCH (input_sl:SourceLocation) WHERE input_sl.url IN [{0}]
    // Then find all the source locations that are upstream or downstream of the input source
    // locations recursively. The resulting `input_and_upstream_sl` variable has all the input
    // source locations and all the upstream or downstream source locations of the input source
    // locations.
    MATCH (input_sl)-[:UPSTREAM*0..]-(input_and_upstream_sl:SourceLocation)
    // Then find all the source locations that embed the source locations in
    // `input_and_upstream_sl` recursively. The resulting `input_upstream_and_embedded_sl`
    // variable will have the contents of the `input_and_upstream_sl` variable previously and
    // all the source locations that eventually embed those source locations.
    MATCH (input_and_upstream_sl)<-[:EMBEDS*0..]-(input_upstream_and_embedded_sl:SourceLocation)
    RETURN ID(input_upstream_and_embedded_sl)
    """.format(', '.join(repr(sl['url']) for sl in source_locations if 'url' in sl))
    results, _ = neomodel.db.cypher_query(query)
    # This should only be true if none of the input source locations are in the DB
    if not results:
        return []
    all_sl_ids = set([r[0] for r in results])

    # Find all the artifacts that were built from the source locations, and those that embed them.
    # Then return the Neo4j IDs of the resulting artifacts.
    query = """
    // First get all the input source locations
    MATCH (sl) WHERE ID(sl) IN [{0}]
    // Find all the artifacts that were built from the source locations, and all the artifacts that
    // embed those artifacts
    MATCH (sl)<-[:BUILT_FROM]-(:Build)-[:PRODUCED]->(:Artifact)<-[:EMBEDS*0..]-(artifact:Artifact)
    RETURN ID(artifact)
    """.format(', '.join(str(sl_id) for sl_id in all_sl_ids))
    results, _ = neomodel.db.cypher_query(query)
    affected_artifact_ids = set([r[0] for r in results])

    # Find all the builds of container artifacts that were built with any of the containers in
    # affected_artifact_ids
    query = """
    // First get all the directly affected container artifacts
    MATCH (affected_container) WHERE ID(affected_container) IN [{0}]
        AND affected_container.type = 'container'
    // Find all the builds of container artifacts that that were built with any of the affected
    // container artifacts
    MATCH (affected_container)<-[:BUILT_WITH]-(:Artifact {{type: 'container'}})
        <-[:PRODUCED]-(built_with_affected_container:Build)
    RETURN built_with_affected_container.id
    """.format(', '.join(repr(artifact_id) for artifact_id in affected_artifact_ids))
    results, _ = neomodel.db.cypher_query(query)
    builds_built_with_affected_container = set([r[0] for r in results])

    # Find all the builds of the container artifacts that embed an artifact that was built with any
    # of the artifacts in affected_artifact_ids
    query = """
    // First get all the artifacts that were built from the source locations
    MATCH (artifact) WHERE ID(artifact) IN [{0}]
    // Find all the container image builds that embed an artifact that was built with an
    // artifact that was built using the source locations.
    MATCH (artifact)<-[:BUILT_WITH]-(:Artifact)<-[:EMBEDS]-(:Artifact {{type: 'container'}})
        <-[:PRODUCED]-(with_built_with_artifact:Build)
    RETURN with_built_with_artifact.id
    """.format(', '.join(repr(artifact_id) for artifact_id in affected_artifact_ids))
    results, _ = neomodel.db.cypher_query(query)
    container_builds_embed_artifact_built_with_sl = set([r[0] for r in results])

    return list(builds_built_with_affected_container.union(
        container_builds_embed_artifact_built_with_sl))
