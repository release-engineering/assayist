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
    type_ = StringProperty(db_property='type', required=True)

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

    TYPES = {
        'rpm': 'rpm',
        'srpm': 'srpm',
        'container': 'container',
        'maven': 'maven',
        'other': 'other',
        # I'm sure we will have more types, feel free to add as needed.
    }

    architecture = StringProperty()
    # Not unique because rpm and archive ids can overlap. Combination of archive_id and type
    # should be unique, but neo4j doesn't do compound unique indexes.
    archive_id = StringProperty(required=True, index=True)
    filename = StringProperty()
    # A one-word description of the type of file this describes (to aid in filtering)
    type_ = StringProperty(required=True, db_property='type', choices=TYPES)

    # The artifacts this artifact is embedded in
    artifacts_embedded_in = RelationshipFrom('Artifact', 'EMBEDS')
    # The artifacts that used this artifact in their buildroot
    artifacts_in_buildroot_for = RelationshipFrom('Artifact', 'BUILT_WITH')
    # The build that produced this artifact
    build = RelationshipFrom('Build', 'PRODUCED', cardinality=ZeroOrOne)
    # The artifacts that were in the buildroot when this artifact was built
    buildroot_artifacts = RelationshipTo('Artifact', 'BUILT_WITH')
    # The external artifacts that were in the buildroot when this artifact was built
    buildroot_external_artifacts = RelationshipTo('ExternalArtifact', 'BUILT_WITH')
    # The checksums associated with this artifact
    checksums = RelationshipFrom('Checksum', 'CHECKSUMS')
    # The artifacts that are embedded in this artifact
    embedded_artifacts = RelationshipTo('Artifact', 'EMBEDS')
    # The external artifacts that are embedded in this artifact
    embedded_external_artifacts = RelationshipTo('ExternalArtifact', 'EMBEDS')
    # The source locations that embedded in this artifact
    embedded_source_locations = RelationshipTo('.source.SourceLocation', 'EMBEDS')
    # The unknown/unclaimed files embedded in this artifact
    unknown_files = RelationshipTo('UnknownFile', 'EMBEDS')


class ExternalArtifact(AssayistStructuredNode):
    """
    The definition of an ExternalArtifact node.

    These represent artifacts that are not built internally and are downloaded directly from
    upstream and used during builds.
    """

    identifier = StringProperty(unique_index=True)
    type_ = StringProperty(index=True, db_property='type')

    # The artifacts that used this external artifact in their buildroot
    artifacts_in_buildroot_for = RelationshipFrom('Artifact', 'BUILT_WITH')
    # The artifacts this external artifact is embedded in
    artifacts_embedded_in = RelationshipFrom('Artifact', 'EMBEDS')
    # The checksums associated with this external artifact
    checksums = RelationshipFrom('Checksum', 'CHECKSUMS')


class Checksum(AssayistStructuredNode):
    """
    The definition of a Checksum node.

    Artifacts have one or more checksums related to their contents. They can vary by hashing
    algorithm, or potentially by signed vs. unsigned status of the binary when the checksum was
    calculated. Providing multiple checksums can also help deduplicate artifact references, and even
    provide a bridge between events originating in different systems.
    """

    # https://neomodel.readthedocs.io/en/latest/properties.html#choices
    CHECKSUM_SOURCES = {
        'signed': 'signed',
        'unsigned': 'unsigned'
    }

    algorithm = StringProperty(required=True)
    checksum = StringProperty(required=True, index=True)
    # A short description of what type of content was checksummed here (signed, unsigned, etc.)
    checksum_source = StringProperty(choices=CHECKSUM_SOURCES)

    # The artifacts this checksum is associated with
    artifacts = RelationshipTo('Artifact', 'CHECKSUMS')
    # The external artifacts this checksum is associated with
    external_artifacts = RelationshipTo('ExternalArtifact', 'CHECKSUMS')

    @staticmethod
    def guess_type(checksum):
        """
        Guess the checksum type from its length.

        :param str checksum: The checksum in question
        :return: The probable type of the Checksum
        :rtype: str
        """
        x = len(checksum)
        if x == 32:
            return 'md5'
        if x == 40:
            return 'sha1'
        if x == 64:
            return 'sha256'
        if x == 128:
            return 'sha512'
        return 'unknown'


class UnknownFile(AssayistStructuredNode):
    """
    The definition of an UnknownFile node.

    Any unclaimed files by analyzers will get UnknownFile nodes created with edges to the artifact
    it's a part of.
    """

    # SHA256 checksum of the file
    checksum = StringProperty(required=True, index=True)
    filename = StringProperty(required=True, index=True)
    # The path to the directory the file is located in
    path = StringProperty(required=True, index=True)

    # The artifacts this unknown file is embedded in
    artifacts = RelationshipFrom('Artifact', 'EMBEDS')
