# SPDX-License-Identifier: GPL-3.0+

from neomodel import StringProperty, ArrayProperty, RelationshipFrom, RelationshipTo, ZeroOrOne, db

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
    alternative_names = ArrayProperty(base_property=StringProperty(), index=True, default=list)

    # The source locations that provide this component
    source_locations = RelationshipFrom('SourceLocation', 'SOURCE_FOR')

    @staticmethod
    def get_or_create(*props, **kwargs):
        """
        Override the get_or_create builtin to ensure it is not accidentally used.

        :param props: anything you want
        :param kwargs: anything you want
        :rtype: RuntimeError
        """
        raise RuntimeError("Don't use the get_or_create builtin, instead use our ",
                           "'get_or_create_singleton' method to ensure alternate names "
                           "are accounted for.")

    @staticmethod
    def create_or_update(*props, **kwargs):
        """
        Override the get_or_create builtin to ensure it is not accidentally used.

        :param props: anything you want
        :param kwargs: anything you want
        :rtype: RuntimeError
        """
        raise RuntimeError("Don't use the get_or_create builtin, instead use our ",
                           "'get_or_create_singleton' method to ensure alternate names "
                           "are accounted for.")

    @staticmethod
    def get_or_create_singleton(canonical_namespace, canonical_name, canonical_type):
        """
        Get or create a single Component, accounting for possible alternative names.

        Note that this function does not have nearly as much functionality as the builtins
        it is replacing, nor is it atomic. I had wanted to alias the builtins too in
        case tests or something really needed them, but I couldn't make that work right.
        However for our use cases this should be a "good enough" implementation of get_or_create.

        :param str canonical_namespace: The namespace for the Component. Required.
        :param str canonical_name: The name for the Component. Returned Component's name
                                   might be different if this matches an alternative_name.
                                   Required.
        :param str canonical_type: The type for the Component. Required.
        :return: The saved component you requested.
        :rtype: Component
        """
        query = """
        MATCH (c:Component {{canonical_type: "{2}", canonical_namespace: "{0}" }})
        WHERE c.canonical_name = "{1}" OR "{1}" in c.alternative_names
        RETURN c
        """.format(canonical_namespace, canonical_name, canonical_type)

        results, _ = db.cypher_query(query)
        if results:
            # There should only be one, because set_component_names de-duplicates as it adds
            # alternative_names.
            assert len(results) == 1
            return Component.inflate(results[0][0])

        return Component(canonical_namespace=canonical_namespace,
                         canonical_name=canonical_name,
                         canonical_type=canonical_type).save()


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
