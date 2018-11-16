# SPDX-License-Identifier: GPL-3.0+

from neomodel import StringProperty, ArrayProperty, RelationshipFrom, RelationshipTo, ZeroOrOne

from assayist.common.models.base import AssayistStructuredNode


class Component(AssayistStructuredNode):
    """
    The definition of a Component node.

    A Component represents what a SourceLocation provides. The canonical name and canonical type
    properties will uniquely identify a component.

    See https://github.com/package-url/purl-spec for information on what makes something canonical.
    """

    canonical_namespace = StringProperty(required=True)
    canonical_name = StringProperty(required=True, index=True)
    canonical_type = StringProperty(required=True, index=True)
    alternative_names = ArrayProperty(base_property=StringProperty(), index=True)

    # The source locations that provide this component
    source_locations = RelationshipFrom('SourceLocation', 'SOURCE_FOR')


class SourceLocation(AssayistStructuredNode):
    """
    The definition of a SourceLocation node.

    A SourceLocation is a source URL + commit information, with a canonical name. It may reference
    a package that was built at least once, or be the location from which other sources were
    vendored into another repository.

    See https://github.com/package-url/purl-spec for information on what makes something canonical.
    """

    TYPES = {
        'local': 'local',
        'upstream': 'upstream',
        '': '',
    }

    canonical_version = StringProperty()
    url = StringProperty(required=True, unique_index=True)
    # A one-word description of the type of repo this describes (to aid in filtering).
    type_ = StringProperty(required=True, db_property='type', choices=TYPES)

    # The artifacts this source location is embedded in
    artifacts_embedded_in = RelationshipFrom('.content.Artifact', 'EMBEDS')
    # The builds this SourceLocation directly produced
    builds = RelationshipFrom('.content.Build', 'BUILT_FROM')
    # The canonical component this SourceLocation provides sources for
    component = RelationshipTo('Component', 'SOURCE_FOR', cardinality=ZeroOrOne)
    # Source locations that are embedded in this source location
    embedded_source_locations = RelationshipTo('SourceLocation', 'EMBEDS')
    # The next version of this artifact
    next_version = RelationshipFrom('SourceLocation', 'SUPERSEDES', cardinality=ZeroOrOne)
    # The previous version of this artifact
    previous_version = RelationshipTo('SourceLocation', 'SUPERSEDES', cardinality=ZeroOrOne)
    # Source locations this source location is embedded in
    source_locations_embedded_in = RelationshipFrom('SourceLocation', 'EMBEDS')
    # The upstream source location for this source location (applies to internal only)
    upstream = RelationshipTo('SourceLocation', 'UPSTREAM')
    # The source locations this source location is the upstream for
    upstream_for = RelationshipFrom('SourceLocation', 'UPSTREAM')
