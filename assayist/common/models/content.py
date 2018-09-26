# SPDX-License-Identifier: GPL-3.0+

from neomodel import StringProperty, RelationshipTo, RelationshipFrom, ZeroOrOne

from assayist.common.models.base import AssayistStructuredNode


class Build(AssayistStructuredNode):
    """
    The definition of a Build node.

    This is a reference to the result of a build. Builds incorporate sources and possibly output
    from other builds, and produce binary outputs (usually archives of some sort).

    The purpose of a Build node is to have a clear path from source location to artifacts without
    having to link each artifact to a particular source location, making traversal of the graph and
    querying easier.
    """

    # Call it "id_" to not overshadow the Neo4j internal ID used by neomodel, but call
    # it "id" in Neo4j
    id_ = StringProperty(db_property='id', required=True, unique_index=True)
    type = StringProperty()

    # TODO: Add the build_composition relationship after it's clearly defined
    # The artifacts that were produced by this build
    artifacts = RelationshipTo('Artifact', 'PRODUCED')
    # The source location used for this build
    source_location = RelationshipTo('.source.SourceLocation', 'BUILT_FROM', cardinality=ZeroOrOne)


class Artifact(AssayistStructuredNode):
    """
    The definition of an Artifact node.

    Artifacts are binary outputs from builds. If the build incorporates binary output from other
    builds, this is where the incorporation will take place.
    """

    architecture = StringProperty()
    archive_id = StringProperty(required=True, unique_index=True)
    checksum = StringProperty()
    filename = StringProperty()

    # The artifacts this artifact is embedded in
    artifacts_embedded_in = RelationshipFrom('Artifact', 'EMBEDS')
    # The artifacts that used this artifact in their buildroot
    artifacts_in_buildroot_for = RelationshipFrom('Artifact', 'BUILT_WITH')
    # The build that produced this artifact
    build = RelationshipFrom('Build', 'PRODUCED', cardinality=ZeroOrOne)
    # The artifacts that were in the buildroot when this artifact was built
    buildroot_artifacts = RelationshipTo('Artifact', 'BUILT_WITH')
    # The artifacts that are embedded in this artifact
    embedded_artifacts = RelationshipTo('Artifact', 'EMBEDS')
    # The source locations that embedded in this artifact
    embedded_source_locations = RelationshipTo('.source.SourceLocation', 'EMBEDS')
